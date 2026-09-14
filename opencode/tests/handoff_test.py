"""Handoff selection, safe publishing and real-Git evidence invalidation."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

TRACKING = Path(__file__).resolve().parents[1] / "tracking"
spec = importlib.util.spec_from_file_location("handoff", TRACKING / "handoff.py")
handoff = importlib.util.module_from_spec(spec)
sys.path.insert(0, str(TRACKING))
try:
    spec.loader.exec_module(handoff)
finally:
    sys.path.pop(0)

ISSUE = {"url": "https://github.com/acme/backend/issues/7", "body": "Reset exactly one preference"}
SOURCE = {"head": "abc", "digest": "state1", "changed_files": ["api.go"]}


def comment(number, stage=None, supersedes=(), body="Evidence"):
    if stage:
        meta = {"stage": stage, "source": SOURCE, "supersedes": list(supersedes)}
        body += "\n<!-- opencode-workflow:v1 " + json.dumps(meta) + " -->"
    return {"id": number, "html_url": ISSUE["url"] + "#issuecomment-" + str(number),
            "updated_at": "2026-09-11T00:00:00Z", "body": body}


class ContextTest(unittest.TestCase):
    def test_old_artifact_bodies_are_not_replayed_but_discussion_is_preserved(self):
        old = comment(1, "research", body="old investigation " * 200)
        new = comment(2, "research", [old["html_url"]], body="current facts")
        decision = comment(3, body="Correction: malformed UUID is 400, not 403")
        review = comment(4, "review", body="prior review should not bias initial review")
        ctx = handoff.select_context(ISSUE, [old, new, decision, review], "plan", current=SOURCE)
        self.assertEqual([c["url"] for c in ctx["selected_artifacts"]], [new["html_url"]])
        self.assertEqual(ctx["discussion"][0]["body"], decision["body"])
        self.assertEqual(len(ctx["artifact_index"]), 3)
        self.assertNotIn("old investigation", json.dumps(ctx))
        self.assertFalse(ctx["ambiguous_artifacts"])

    def test_multiple_plans_require_selection_not_latest_wins(self):
        first, second = comment(1, "plan"), comment(2, "plan")
        ctx = handoff.select_context(ISSUE, [first, second], "execute", current=SOURCE)
        self.assertEqual(len(ctx["ambiguous_artifacts"]), 1)
        self.assertEqual(ctx["selected_artifacts"], [])
        pinned = handoff.select_context(ISSUE, [first, second], "execute", [first["html_url"]], SOURCE)
        self.assertFalse(pinned["ambiguous_artifacts"])
        self.assertEqual(pinned["selected_artifacts"][0]["url"], first["html_url"])

    def test_old_explicit_plan_does_not_hide_later_discussion(self):
        old = comment(1, "plan")
        correction = comment(2, body="The scope changed; do not implement the old endpoint")
        ctx = handoff.select_context(ISSUE, [old, correction], "execute", [old["html_url"]], SOURCE)
        self.assertEqual(ctx["discussion"][0]["body"], correction["body"])

    def test_foreign_or_missing_comment_is_rejected(self):
        c = comment(1, "plan")
        for url in ("https://github.com/acme/backend/issues/8#issuecomment-1", ISSUE["url"] + "#issuecomment-999"):
            with self.assertRaises(RuntimeError):
                handoff.select_context(ISSUE, [c], "execute", [url], SOURCE)

    def test_legacy_and_malformed_metadata_remain_visible(self):
        legacy = comment(1, body="## Implementation plan\nLegacy plan")
        malformed = comment(2, body='Decision\n<!-- opencode-workflow:v1 {"stage":"plan","source":null} -->')
        ctx = handoff.select_context(ISSUE, [legacy, malformed], "execute", [legacy["html_url"]], SOURCE)
        self.assertEqual(len(ctx["discussion"]), 2)
        self.assertIsNone(ctx["selected_artifacts"][0]["metadata"])

    def test_changed_source_invalidates_evidence(self):
        c = comment(1, "verification")
        ctx = handoff.select_context(ISSUE, [c], "review", current={**SOURCE, "digest": "changed"})
        self.assertFalse(ctx["selected_artifacts"][0]["matches_current_state"])

    def test_repair_sees_current_review_but_initial_review_does_not_replay_it(self):
        prior = comment(1, "review", body="Fix malformed UUID validation")
        repair = handoff.select_context(ISSUE, [prior], "execute", current=SOURCE)
        initial = handoff.select_context(ISSUE, [prior], "review", current=SOURCE)
        self.assertEqual(repair["selected_artifacts"][0]["url"], prior["html_url"])
        self.assertEqual(initial["selected_artifacts"], [])

    def test_empty_artifact_cannot_publish_a_pass(self):
        with patch.object(handoff.track, "run") as run:
            with self.assertRaisesRegex(RuntimeError, "empty"):
                handoff.publish(ISSUE, [], "review", " \n", SOURCE, verdict="pass")
            run.assert_not_called()

    def test_publish_retry_returns_same_url_without_second_write(self):
        url = ISSUE["url"] + "#issuecomment-20"
        with patch.object(handoff.track, "run", return_value=url) as run:
            result = handoff.publish(ISSUE, [], "review", "All required checks pass", SOURCE, verdict="pass")
            body = run.call_args.args[-1]
        existing = comment(20, body=body)
        with patch.object(handoff.track, "run") as run:
            retry = handoff.publish(ISSUE, [existing], "review", "All required checks pass", SOURCE, verdict="pass")
            run.assert_not_called()
        self.assertEqual(result["url"], retry["url"])
        self.assertEqual(retry["outcome"], "already_published")

    def test_review_requires_verdict_and_cross_stage_supersession_is_rejected(self):
        with self.assertRaises(RuntimeError):
            handoff.publish(ISSUE, [], "review", "Reviewed", SOURCE)
        c = comment(1, "plan")
        with self.assertRaises(RuntimeError):
            handoff.publish(ISSUE, [c], "research", "Facts", SOURCE, supersedes=[c["html_url"]])

    def test_repository_mismatch_prevents_handoff(self):
        with patch.object(handoff.track, "issue_details", return_value={"url": ISSUE["url"], "repository": "acme/backend", "number": 7}):
            with patch.object(handoff.track, "gh", return_value={"nameWithOwner": "other/repo"}) as gh:
                with self.assertRaisesRegex(RuntimeError, "differs"):
                    handoff.issue_and_comments("7")
                self.assertEqual(gh.call_count, 1)


class SnapshotTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        env = patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "Test", "GIT_COMMITTER_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.invalid", "GIT_COMMITTER_EMAIL": "test@example.invalid"})
        env.start(); self.addCleanup(env.stop)
        self.git("init", "-b", "main")
        (self.root / "api.go").write_text("base\n")
        self.git("add", "api.go"); self.git("commit", "-m", "base")

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.root, stderr=subprocess.PIPE)

    def digest(self):
        return handoff.snapshot(self.root)["digest"]

    def test_staging_same_content_preserves_digest_but_edits_invalidate(self):
        (self.root / "api.go").write_text("implementation\n")
        (self.root / "new test.go").write_text("regression\n")
        before = self.digest()
        self.git("add", "api.go", "new test.go")
        self.assertEqual(before, self.digest())
        (self.root / "api.go").write_text("unreviewed edit\n")
        self.assertNotEqual(before, self.digest())

    def test_cancelled_worktree_edit_still_binds_partial_index(self):
        clean = self.digest()
        (self.root / "api.go").write_text("staged change\n"); self.git("add", "api.go")
        (self.root / "api.go").write_text("base\n")
        partial = handoff.snapshot(self.root)
        self.assertNotEqual(clean, partial["digest"])
        self.assertEqual(partial["partially_staged_files"], ["api.go"])
        (self.root / "api.go").write_text("different staged change\n"); self.git("add", "api.go")
        (self.root / "api.go").write_text("base\n")
        self.assertNotEqual(partial["digest"], self.digest())

    def test_untracked_symlinks_are_hashed_without_following_target(self):
        (self.root / "external").symlink_to("/does/not/exist")
        before = self.digest()
        self.git("add", "external")
        self.assertEqual(before, self.digest())
        (self.root / "external").unlink()
        (self.root / "external").symlink_to("/different/target")
        self.assertNotEqual(before, self.digest())

    def test_read_only_snapshot_does_not_change_index_or_worktree(self):
        (self.root / "api.go").write_text("edit\n")
        status = self.git("status", "--porcelain")
        index = (self.root / ".git/index").read_bytes()
        self.digest()
        self.assertEqual(index, (self.root / ".git/index").read_bytes())
        self.assertEqual(status, self.git("status", "--porcelain"))


if __name__ == "__main__":
    unittest.main()
