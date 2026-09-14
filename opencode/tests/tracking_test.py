"""Real local Git histories; GitHub mutations intercepted. No network or user refs."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import call, patch

spec = importlib.util.spec_from_file_location("track", Path(__file__).resolve().parents[1] / "tracking/track.py")
track = importlib.util.module_from_spec(spec)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tracking"))
try:
    spec.loader.exec_module(track)
finally:
    sys.path.pop(0)
ISSUE = "https://github.com/example-org/backend/issues/123"
REAL_SET_FIELD = track.set_field


class TrackingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = patch.dict(os.environ, {
            "GIT_AUTHOR_NAME": "Tracking Test", "GIT_COMMITTER_NAME": "Tracking Test",
            "GIT_AUTHOR_EMAIL": "test@example.invalid", "GIT_COMMITTER_EMAIL": "test@example.invalid",
            "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.state = patch.object(track, "STATE", self.root / "state")
        self.state.start()
        self.addCleanup(self.state.stop)
        self.origin = self.root / "origin.git"
        self.repo = self.root / "repo"
        self.work = self.root / "parallel work"
        self.cmd("git", "init", "--bare", str(self.origin))
        self.cmd("git", "init", "-b", "main", str(self.repo))
        (self.repo / "shared.txt").write_text("base\n")
        self.g(self.repo, "add", "shared.txt")
        self.g(self.repo, "commit", "-m", "initial")
        self.g(self.repo, "remote", "add", "origin", str(self.origin))
        self.g(self.repo, "push", "-u", "origin", "main")
        self.g(self.repo, "worktree", "add", "-b", "feature", str(self.work))
        self.record = dict(path=str(self.work), common=str(self.repo / ".git"), branch="feature", target="main", state="Up to date", observed=None)
        self.mutations = []
        self.notes = []
        for name, replacement in [
            ("set_field", lambda *args: self.mutations.append(args)),
            ("note", lambda *args: self.notes.append(args)),
            ("gh", lambda *args: {"state": "OPEN"}),
        ]:
            p = patch.object(track, name, replacement)
            p.start()
            self.addCleanup(p.stop)
        self.save()

    def cmd(self, *args, cwd=None):
        return subprocess.check_output(args, cwd=cwd, stderr=subprocess.STDOUT, text=True).strip()

    def g(self, path, *args):
        return self.cmd("git", *args, cwd=path)

    def save(self):
        with track.registry() as data:
            data[ISSUE] = self.record.copy()

    def load(self):
        with track.registry() as data:
            return data[ISSUE].copy()

    def advance(self):
        (self.repo / "shared.txt").write_text("main change\n")
        self.g(self.repo, "commit", "-am", "advance main")
        self.g(self.repo, "push", "origin", "main")

    def test_parallel_branch_detected_without_worktree_mutation(self):
        head = self.g(self.work, "rev-parse", "HEAD")
        (self.work / "dirty.txt").write_text("user work\n")
        self.advance()
        track.refresh()
        self.assertEqual(self.load()["state"], "Needs sync")
        self.assertEqual(self.g(self.work, "rev-parse", "HEAD"), head)
        self.assertEqual((self.work / "dirty.txt").read_text(), "user work\n")
        self.assertEqual(len(self.notes), 1)
        track.refresh()
        self.assertEqual(len(self.notes), 1)

    def test_explicit_merge_requires_verification(self):
        self.advance()
        track.sync_state(ISSUE, "Syncing")
        self.g(self.work, "fetch", "origin")
        self.g(self.work, "merge", "origin/main")
        track.refresh()
        self.assertEqual(self.load()["state"], "Verifying")
        with self.assertRaises(RuntimeError):
            track.sync_state(ISSUE, "Up to date")
        evidence = self.root / "checks.md"
        evidence.write_text("git diff --check: passed; shared.txt verified\n")
        track.sync_state(ISSUE, "Up to date", str(evidence))
        self.assertEqual(self.load()["state"], "Up to date")

    def conflict(self, operation):
        (self.work / "shared.txt").write_text("feature change\n")
        self.g(self.work, "commit", "-am", "feature")
        self.advance()
        self.g(self.work, "fetch", "origin")
        track.sync_state(ISSUE, "Syncing")
        with self.assertRaises(subprocess.CalledProcessError):
            self.g(self.work, operation, "origin/main")
        track.refresh()
        self.assertEqual(self.load()["state"], "Conflicts")

    def test_merge_conflict_and_resolution(self):
        self.conflict("merge")
        (self.work / "shared.txt").write_text("main change\nfeature change\n")
        self.g(self.work, "add", "shared.txt")
        self.g(self.work, "commit", "-m", "resolve")
        track.refresh()
        self.assertEqual(self.load()["state"], "Verifying")

    def test_detached_rebase_conflict_is_detected(self):
        self.conflict("rebase")
        self.g(self.work, "rebase", "--abort")
        track.refresh()
        self.assertEqual(self.load()["state"], "Verifying")

    def test_renamed_worktree_is_recovered(self):
        moved = self.root / "renamed work"
        self.g(self.repo, "worktree", "move", str(self.work), str(moved))
        track.refresh()
        self.assertEqual(Path(self.load()["path"]).resolve(), moved.resolve())
        self.assertEqual(self.load()["state"], "Up to date")

    def test_renamed_branch_is_not_silently_reassigned(self):
        self.g(self.work, "branch", "-m", "different")
        with self.assertRaises(RuntimeError):
            track.refresh()
        self.assertEqual(self.load()["state"], "Unchecked")
        self.assertEqual(self.load()["branch"], "feature")

    def test_offline_preserves_verification_then_recovers(self):
        self.record["state"] = "Verifying"
        self.save()
        with patch.object(track, "inspect", side_effect=RuntimeError("offline")):
            with self.assertRaises(RuntimeError):
                track.refresh()
        self.assertEqual(self.load()["state"], "Verifying")
        self.assertEqual(self.load()["error"], "offline")
        track.refresh()
        self.assertIsNone(self.load()["error"])
        self.assertEqual(self.load()["state"], "Verifying")

    def test_main_moves_before_verification(self):
        self.record["state"] = "Verifying"
        self.save()
        self.advance()
        evidence = self.root / "checks.md"
        evidence.write_text("checks passed against previous main\n")
        with self.assertRaises(RuntimeError):
            track.sync_state(ISSUE, "Up to date", str(evidence))
        self.assertEqual(self.load()["state"], "Verifying")

    def test_failed_github_write_retries(self):
        self.advance()
        with patch.object(track, "set_field", side_effect=RuntimeError("GitHub offline")):
            with self.assertRaises(RuntimeError):
                track.refresh()
        self.assertNotEqual(self.load()["state"], "Needs sync")
        track.refresh()
        self.assertEqual(self.load()["state"], "Needs sync")

    def test_closed_issue_does_not_imply_done(self):
        with patch.object(track, "gh", return_value={"state": "CLOSED"}):
            track.refresh()
        self.assertFalse(self.mutations)

    def test_issue_only_refresh_and_sync_keep_local_state_without_project_writes(self):
        with patch.object(track, "set_field", REAL_SET_FIELD), \
             patch.object(track, "load_private_config", return_value={}), \
             patch.object(track, "project", side_effect=AssertionError("project operation in issue-only mode")):
            self.advance()
            track.refresh()
            self.assertEqual(self.load()["state"], "Needs sync")
            self.assertEqual(len(self.notes), 1)
            track.sync_state(ISSUE, "Syncing")
            self.assertEqual(self.load()["state"], "Syncing")
        self.assertFalse(self.mutations)

    def test_issue_only_registers_actual_feature_worktree_without_a_board(self):
        with track.registry() as data:
            data.clear()
        self.g(self.work, "remote", "set-url", "origin", "https://github.com/example-org/backend.git")
        real_git = track.git
        with patch.object(track, "set_field", REAL_SET_FIELD), \
             patch.object(track, "load_private_config", return_value={}), \
             patch.object(track, "project", side_effect=AssertionError("unexpected board operation")), \
             patch.object(track, "git", side_effect=lambda cwd, *args: real_git(cwd or self.work, *args)), \
             patch.object(track, "gh", return_value={"nameWithOwner": "example-org/backend", "defaultBranchRef": {"name": "main"}}):
            track.register(ISSUE)
        self.assertEqual(self.load()["branch"], "feature")
        self.assertEqual(Path(self.load()["path"]).resolve(), self.work.resolve())
        self.assertEqual(self.load()["state"], "Unchecked")
        self.assertEqual(len(self.notes), 1)


class IssueOnlyTest(unittest.TestCase):
    def test_combined_status_does_not_require_optional_orca_cli(self):
        with patch.object(track, "load_private_config", return_value={}), \
             patch.object(track, "checkpoint_orca", return_value=({"outcome": "failed", "reason": "orca_unavailable"}, 1)):
            result, code = track.workflow_status(ISSUE, "Implementing")
        self.assertEqual(code, 0)
        self.assertEqual(result["orca"]["outcome"], "not_configured")

    def test_configured_board_uses_selected_owner_and_number(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.json"
            config.write_text('{"version":1,"tracking":{"owner":"example-org","number":7}}')
            with patch.dict(os.environ, {"OPENCODE_PRIVATE_CONFIG": str(config)}), \
                 patch.object(track, "gh", side_effect=[{"id": "project-id"}, {"fields": []}]) as api:
                self.assertEqual(track.project(), ("project-id", {}))
            self.assertEqual(api.call_args_list, [
                call("project", "view", "7", "--owner", "example-org", "--format", "json"),
                call("project", "field-list", "7", "--owner", "example-org", "--limit", "100", "--format", "json")])

    def test_status_reports_skipped_board_and_malformed_config_is_not_a_skip(self):
        with patch.object(track, "load_private_config", return_value={}), \
             patch.object(track, "checkpoint_orca", return_value=({"outcome": "not_managed"}, 0)), \
             patch.object(track, "project") as project:
            result, code = track.workflow_status(ISSUE, "Implementing")
            self.assertEqual(code, 0)
            self.assertEqual(result["github"], {"outcome": "not_configured"})
            project.assert_not_called()
        with patch.object(track, "load_private_config", side_effect=RuntimeError("invalid config")):
            with self.assertRaisesRegex(RuntimeError, "invalid config"):
                track.set_field(ISSUE, "Status", "Ready")


class CommentTest(unittest.TestCase):
    def test_comment_retry_checks_all_pages(self):
        with patch.object(track, "gh", return_value=[[{"body": "first"}], [{"body": "<!-- opencode-track:key -->"}]]) as api:
            with patch.object(track, "run") as write:
                track.note(ISSUE, "Research", "body", "key")
                write.assert_not_called()
                self.assertIn("--paginate", api.call_args.args)


class IssueUrlTest(unittest.TestCase):
    def test_accepts_issue_outside_tracking_organization(self):
        value = "https://github.com/example-user/sample/issues/4"
        with patch.object(track, "gh", return_value={"number": 4, "url": value}) as api:
            self.assertEqual(track.issue_url(value), value)
        api.assert_called_once_with("issue", "view", value, "--json", "number,url")

    def test_uses_canonical_github_identity(self):
        supplied = "https://github.com/EXAMPLE-USER/SAMPLE/issues/4"
        canonical = "https://github.com/example-user/sample/issues/4"
        with patch.object(track, "gh", return_value={"number": 4, "url": canonical}):
            self.assertEqual(track.issue_details(supplied), {
                "number": 4, "repository": "example-user/sample", "url": canonical
            })

    def test_rejects_mismatched_github_number(self):
        value = "https://github.com/example-user/sample/issues/4"
        with patch.object(track, "gh", return_value={"number": 5, "url": value}):
            with self.assertRaisesRegex(RuntimeError, "invalid issue number"):
                track.issue_details(value)

    def test_number_resolves_against_current_repository(self):
        value = "https://github.com/example-user/sample/issues/4"
        with patch.object(track, "gh", side_effect=[
            {"nameWithOwner": "example-user/sample"}, {"number": 4, "url": value}
        ]) as api:
            self.assertEqual(track.issue_url("4"), value)
        self.assertEqual(api.call_args_list, [
            call("repo", "view", "--json", "nameWithOwner"),
            call("issue", "view", value, "--json", "number,url"),
        ])

    def test_rejects_malformed_github_json(self):
        value = "https://github.com/example-user/sample/issues/4"
        error = json.JSONDecodeError("bad", "", 0)
        with patch.object(track, "gh", side_effect=error):
            with self.assertRaisesRegex(RuntimeError, "invalid JSON"):
                track.issue_details(value)

    def test_rejects_malformed_numeric_repository_response(self):
        with patch.object(track, "gh", return_value=[]):
            with self.assertRaisesRegex(RuntimeError, "repository identity"):
                track.issue_details("4")


class OrcaProtocolTest(unittest.TestCase):
    def completed(self, response, returncode=0, stderr=""):
        return subprocess.CompletedProcess(
            args=[], returncode=returncode, stdout=response, stderr=stderr
        )

    def test_preserves_structured_error_code(self):
        response = json.dumps({
            "ok": False, "error": {"code": "selector_not_found", "message": "outside"}
        })
        with patch.object(track.subprocess, "run", return_value=self.completed(response)):
            with self.assertRaises(track.OrcaError) as raised:
                track.orca("worktree", "current", "--json")
        self.assertEqual(raised.exception.reason, "selector_not_found")

    def test_rejects_malformed_json(self):
        with patch.object(track.subprocess, "run", return_value=self.completed("not json")):
            with self.assertRaises(track.OrcaError) as raised:
                track.orca("worktree", "current", "--json")
        self.assertEqual(raised.exception.reason, "malformed_orca_response")

    def test_rejects_non_object_envelope(self):
        with patch.object(track.subprocess, "run", return_value=self.completed("[]")):
            with self.assertRaises(track.OrcaError) as raised:
                track.orca("worktree", "current", "--json")
        self.assertEqual(raised.exception.reason, "malformed_orca_response")

    def test_rejects_non_boolean_ok(self):
        response = json.dumps({"ok": 1, "result": {}})
        with patch.object(track.subprocess, "run", return_value=self.completed(response)):
            with self.assertRaises(track.OrcaError) as raised:
                track.orca("worktree", "current", "--json")
        self.assertEqual(raised.exception.reason, "malformed_orca_response")

    def test_rejects_nonzero_success_envelope(self):
        response = json.dumps({"ok": True, "result": {}})
        with patch.object(track.subprocess, "run", return_value=self.completed(response, 1)):
            with self.assertRaises(track.OrcaError) as raised:
                track.orca("worktree", "current", "--json")
        self.assertEqual(raised.exception.reason, "orca_process_error")

    def test_classifies_missing_executable(self):
        with patch.object(track.subprocess, "run", side_effect=FileNotFoundError):
            with self.assertRaises(track.OrcaError) as raised:
                track.orca("worktree", "current", "--json")
        self.assertEqual(raised.exception.reason, "orca_unavailable")

    def test_classifies_timeout(self):
        with patch.object(track.subprocess, "run", side_effect=subprocess.TimeoutExpired("orca", 90)):
            with self.assertRaises(track.OrcaError) as raised:
                track.orca("worktree", "current", "--json")
        self.assertEqual(raised.exception.reason, "orca_timeout")


class OrcaLinkTest(unittest.TestCase):
    ISSUE = "https://github.com/example-user/sample/issues/4"
    DETAILS = {"number": 4, "repository": "example-user/sample", "url": ISSUE}
    WORKTREE_ID = "repo-id::/worktree"

    def worktree(self, linked=None, project="github:example-user/sample", path="/worktree", worktree_id=None):
        return {"ok": True, "result": {"worktree": {
            "id": worktree_id or self.WORKTREE_ID,
            "projectId": project,
            "path": path,
            "linkedIssue": linked,
        }}}

    def link(self, responses, replace_existing=None):
        with patch.object(track, "issue_details", return_value=self.DETAILS.copy()):
            with patch.object(track, "orca", side_effect=responses) as api:
                result, exit_code = track.link_orca(self.ISSUE, replace_existing)
        return result, exit_code, api

    def test_attaches_empty_link_and_verifies_exact_worktree(self):
        result, exit_code, api = self.link([
            self.worktree(), self.worktree(4), self.worktree(4)
        ])
        self.assertEqual((result["outcome"], exit_code), ("attached", 0))
        self.assertEqual(api.call_args_list, [
            call("worktree", "current", "--json"),
            call("worktree", "set", "--worktree", "id:" + self.WORKTREE_ID,
                 "--issue", "4", "--json"),
            call("worktree", "current", "--json"),
        ])

    def test_matching_link_is_idempotent(self):
        result, exit_code, api = self.link([self.worktree(4)])
        self.assertEqual((result["outcome"], exit_code), ("already_attached", 0))
        api.assert_called_once_with("worktree", "current", "--json")

    def test_conflicting_link_is_preserved(self):
        result, exit_code, api = self.link([self.worktree(3)])
        self.assertEqual((result["outcome"], exit_code), ("conflict", 2))
        self.assertEqual(result["existingIssue"], 3)
        self.assertTrue(result["recoveryCommand"].endswith("--replace-existing 3"))
        api.assert_called_once_with("worktree", "current", "--json")

    def test_approved_observed_link_can_be_replaced(self):
        result, exit_code, api = self.link([
            self.worktree(3), self.worktree(4), self.worktree(4)
        ], replace_existing=3)
        self.assertEqual((result["outcome"], exit_code), ("attached", 0))
        self.assertEqual(api.call_count, 3)

    def test_stale_replacement_authorization_is_refused(self):
        result, exit_code, api = self.link([self.worktree()], replace_existing=3)
        self.assertEqual((result["reason"], exit_code), ("stale_replacement", 2))
        self.assertFalse(result["recoveryCommand"].endswith("--replace-existing 3"))
        api.assert_called_once_with("worktree", "current", "--json")

    def test_changed_link_requires_new_specific_authorization(self):
        result, exit_code, api = self.link([self.worktree(5)], replace_existing=3)
        self.assertEqual((result["reason"], exit_code), ("stale_replacement", 2))
        self.assertEqual(result["observed"], 3)
        self.assertTrue(result["recoveryCommand"].endswith("--replace-existing 5"))
        self.assertNotIn("--replace-existing 3 --replace-existing", result["recoveryCommand"])
        api.assert_called_once_with("worktree", "current", "--json")

    def test_unmanaged_directory_is_not_a_failure(self):
        result, exit_code, _ = self.link([
            track.OrcaError("selector_not_found", "outside")
        ])
        self.assertEqual((result["outcome"], exit_code), ("not_managed", 0))
        self.assertNotIn("recoveryCommand", result)

    def test_missing_orca_is_recoverable(self):
        result, exit_code, _ = self.link([
            track.OrcaError("orca_unavailable", "missing")
        ])
        self.assertEqual((result["outcome"], exit_code), ("orca_unavailable", 0))
        self.assertIn(self.ISSUE, result["recoveryCommand"])

    def test_runtime_unavailable_is_attachment_failure(self):
        result, exit_code, _ = self.link([
            track.OrcaError("runtime_unavailable", "stopped")
        ])
        self.assertEqual((result["reason"], exit_code), ("runtime_unavailable", 1))

    def test_remote_runtime_error_is_classified_narrowly(self):
        result, exit_code, _ = self.link([track.OrcaError(
            "invalid_argument", "current is a local cwd shortcut against a remote runtime"
        )])
        self.assertEqual((result["reason"], exit_code), ("remote_runtime_unsupported", 1))

    def test_repository_mismatch_refuses_mutation(self):
        result, exit_code, api = self.link([
            self.worktree(project="github:someone/else")
        ])
        self.assertEqual((result["reason"], exit_code), ("repository_mismatch", 1))
        self.assertEqual(result["worktree"]["id"], self.WORKTREE_ID)
        api.assert_called_once_with("worktree", "current", "--json")

    def test_repository_match_is_case_insensitive(self):
        result, exit_code, _ = self.link([
            self.worktree(4, project="github:EXAMPLE-USER/SAMPLE")
        ])
        self.assertEqual((result["outcome"], exit_code), ("already_attached", 0))

    def test_malformed_linked_issue_refuses_mutation(self):
        result, exit_code, api = self.link([self.worktree("4")])
        self.assertEqual((result["reason"], exit_code), ("malformed_linked_issue", 1))
        api.assert_called_once_with("worktree", "current", "--json")

    def test_setter_failure_reports_recovery(self):
        result, exit_code, _ = self.link([
            self.worktree(), track.OrcaError("runtime_error", "write failed")
        ])
        self.assertEqual((result["reason"], exit_code), ("setter_error", 1))
        self.assertIn("link-orca " + self.ISSUE, result["recoveryCommand"])

    def test_setter_confirmation_must_match(self):
        result, exit_code, api = self.link([self.worktree(), self.worktree(3)])
        self.assertEqual((result["reason"], exit_code), ("invalid_setter_confirmation", 1))
        self.assertEqual(api.call_count, 2)

    def test_setter_confirmation_must_keep_path(self):
        result, exit_code, _ = self.link([
            self.worktree(), self.worktree(4, path="/other")
        ])
        self.assertEqual((result["reason"], exit_code), ("invalid_setter_confirmation", 1))

    def test_final_verification_must_match_identity_and_issue(self):
        result, exit_code, _ = self.link([
            self.worktree(), self.worktree(4), self.worktree(3)
        ])
        self.assertEqual((result["reason"], exit_code), ("verification_mismatch", 1))

    def test_final_verification_must_keep_worktree_id(self):
        result, exit_code, _ = self.link([
            self.worktree(), self.worktree(4), self.worktree(4, worktree_id="other")
        ])
        self.assertEqual((result["reason"], exit_code), ("verification_mismatch", 1))

    def test_orca_error_data_is_preserved(self):
        result, exit_code, _ = self.link([
            track.OrcaError("runtime_unavailable", "stopped", {"nextSteps": ["orca open"]})
        ])
        self.assertEqual(exit_code, 1)
        self.assertEqual(result["details"], {"nextSteps": ["orca open"]})


class OrcaCheckpointTest(unittest.TestCase):
    ISSUE = OrcaLinkTest.ISSUE
    DETAILS = OrcaLinkTest.DETAILS
    WORKTREE_ID = OrcaLinkTest.WORKTREE_ID

    def worktree(self, comment="", status="in-progress", linked=4, **kwargs):
        response = OrcaLinkTest.worktree(self, linked=linked, **kwargs)
        response["result"]["worktree"].update(comment=comment, workspaceStatus=status)
        return response

    def checkpoint(self, responses, stage="Implementing", summary="tests running"):
        with patch.object(track, "issue_details", return_value=self.DETAILS.copy()):
            with patch.object(track, "orca", side_effect=responses) as api:
                result, code = track.checkpoint_orca(self.ISSUE, stage, summary)
        return result, code, api

    def test_preserves_user_notes_and_replaces_only_owned_issue_line(self):
        old = "goal: retain API compatibility\n[opencode-workflow #4] Ready: old\n[opencode-workflow #9] other work"
        new = "[opencode-workflow #4] Implementing: tests running\ngoal: retain API compatibility\n[opencode-workflow #9] other work"
        result, code, api = self.checkpoint([self.worktree(old), self.worktree(new), self.worktree(new)])
        self.assertEqual((result["outcome"], code), ("updated", 0))
        self.assertEqual(api.call_args_list[1], call(
            "worktree", "set", "--worktree", "id:" + self.WORKTREE_ID,
            "--comment", new, "--workspace-status", "in-progress", "--json"))
        self.assertEqual(api.call_args_list[2], call("worktree", "show", "--worktree", "id:" + self.WORKTREE_ID, "--json"))

    def test_identical_checkpoint_does_not_write(self):
        comment = "[opencode-workflow #4] Implementing: tests running"
        result, code, api = self.checkpoint([self.worktree(comment)])
        self.assertEqual((result["outcome"], code, api.call_count), ("already_updated", 0, 1))

    def test_wrong_or_missing_link_never_updates_card(self):
        for linked, outcome in [(None, "not_linked"), (9, "conflict")]:
            with self.subTest(linked=linked):
                result, code, api = self.checkpoint([self.worktree(linked=linked)])
                self.assertEqual((result["outcome"], code, api.call_count), (outcome, 2, 1))

    def test_wrong_repository_never_updates_card(self):
        result, code, api = self.checkpoint([self.worktree(project="github:other/repo")])
        self.assertEqual((result["reason"], code, api.call_count), ("repository_mismatch", 1, 1))

    def test_unmanaged_is_noop_but_unavailable_reports_recovery(self):
        result, code, _ = self.checkpoint([track.OrcaError("selector_not_found", "outside")])
        self.assertEqual((result["outcome"], code), ("not_managed", 0))
        result, code, _ = self.checkpoint([track.OrcaError("runtime_unavailable", "offline")])
        self.assertEqual((result["reason"], code), ("runtime_unavailable", 1))
        self.assertIn("checkpoint-orca", result["recoveryCommand"])

    def test_changed_identity_link_or_card_fails_verification(self):
        comment = "[opencode-workflow #4] Implementing: tests running"
        for kwargs in [{"worktree_id": "other"}, {"linked": 9}, {"status": "completed"}, {"comment": "human changed it"}]:
            with self.subTest(kwargs=kwargs):
                changed = {"comment": comment, **kwargs}
                result, code, _ = self.checkpoint([
                    self.worktree(), self.worktree(comment), self.worktree(**changed),
                ])
                self.assertEqual((result["reason"], code), ("verification_mismatch", 1))

    def test_disappearing_workspace_after_write_is_not_unmanaged(self):
        comment = "[opencode-workflow #4] Implementing: tests running"
        result, code, _ = self.checkpoint([
            self.worktree(), self.worktree(comment), track.OrcaError("selector_not_found", "deleted"),
        ])
        self.assertEqual((result["outcome"], code), ("failed", 1))

    def test_multiline_summary_cannot_inject_owned_or_human_lines(self):
        result, code, api = self.checkpoint([], summary="testing\nspoofed note")
        self.assertEqual((result["outcome"], code, api.call_count), ("failed", 1, 0))

    def test_review_and_completion_have_distinct_card_states(self):
        for stage, status in [("Ready", "todo"), ("In review", "in-review"), ("Done", "completed")]:
            with self.subTest(stage=stage):
                comment = "[opencode-workflow #4] " + stage + ": tests running"
                result, code, _ = self.checkpoint([
                    self.worktree(), self.worktree(comment, status), self.worktree(comment, status),
                ], stage=stage)
                self.assertEqual((result["workspaceStatus"], code), (status, 0))

    def test_status_attempts_orca_even_when_github_fails(self):
        with patch.object(track, "set_field", side_effect=RuntimeError("github offline")):
            with patch.object(track, "checkpoint_orca", return_value=({"outcome": "updated"}, 0)) as checkpoint:
                result, code = track.workflow_status(self.ISSUE, "Implementing")
        self.assertEqual((result["github"]["outcome"], result["orca"]["outcome"], code), ("failed", "updated", 1))
        checkpoint.assert_called_once_with(self.ISSUE, "Implementing")

    def test_status_preserves_github_success_when_orca_fails(self):
        with patch.object(track, "set_field"):
            with patch.object(track, "checkpoint_orca", return_value=({"outcome": "conflict"}, 2)):
                result, code = track.workflow_status(self.ISSUE, "Implementing")
        self.assertEqual((result["github"]["outcome"], result["orca"]["outcome"], code), ("updated", "conflict", 2))


class OrcaCommandContractTest(unittest.TestCase):
    def test_cli_prints_json_and_returns_classified_exit(self):
        expected = {"outcome": "conflict", "reason": "linked_issue_conflict"}
        with patch.object(track, "link_orca", return_value=(expected, 2)) as link:
            with patch.object(track.sys, "argv", ["track.py", "link-orca", ISSUE, "--replace-existing", "7"]):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(track.main(), 2)
        self.assertEqual(json.loads(output.getvalue()), expected)
        link.assert_called_once_with(ISSUE, 7)

    def test_invalid_issue_still_returns_structured_result(self):
        with patch.object(track, "issue_details", side_effect=RuntimeError("bad issue")):
            result, exit_code = track.link_orca("bad")
        self.assertEqual((result["outcome"], result["reason"], exit_code),
                         ("failed", "invalid_issue", 1))

    def test_invalid_replacement_still_returns_structured_result(self):
        with patch.object(track.sys, "argv", ["track.py", "link-orca", ISSUE, "--replace-existing", "0"]):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(track.main(), 1)
        result = json.loads(output.getvalue())
        self.assertEqual((result["outcome"], result["reason"]),
                         ("failed", "invalid_replacement"))

    def test_ticket_contract_separates_new_issue_attachment(self):
        root = Path(__file__).resolve().parents[1]
        command = (root / "commands/ticket.md").read_text()
        self.assertIn("workflow-ticket", command)
        contract = " ".join((root / "skills/workflow/workflow-ticket/SKILL.md").read_text().split())
        self.assertIn("link-orca ISSUE", contract)
        self.assertIn("Keep existing link (Recommended)", contract)
        self.assertIn("Return issue creation/update, assignee/configured-project fields, and Orca attachment as separate outcomes", contract)
        self.assertIn("or invoke `link-orca`", contract)
        self.assertLess(contract.index("gh issue create"), contract.index("link-orca ISSUE"))
        self.assertIn("neither downstream failure undoes the created issue or excuses skipping the other outcome", contract)


if __name__ == "__main__":
    unittest.main()
