"""Real-Git v2 handoffs: edits, gates, repairs, logs, and safe compaction."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

TRACKING = Path(__file__).resolve().parents[1] / "tracking"
sys.path.insert(0, str(TRACKING))
import handoff
import packet
import verify
import workflow_state as state
import operational
sys.path.pop(0)

TEST_PROGRAM = "import unittest\nclass Example(unittest.TestCase):\n def test_value(self): self.assertEqual(2+2,4)\nunittest.main()\n"


class PacketTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repo"
        self.root.mkdir()
        env = patch.dict(os.environ, {"OPENCODE_WORKFLOW_STATE": str(Path(self.tmp.name) / "state"),
            "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "GIT_AUTHOR_NAME": "Test",
            "GIT_COMMITTER_NAME": "Test", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_EMAIL": "t@example.invalid"})
        env.start(); self.addCleanup(env.stop)
        self.git("init", "-b", "main")
        (self.root / "api.txt").write_text("base\n")
        self.git("add", "."); self.git("commit", "-m", "base")
        self.issue = {"url": "https://github.com/example/repo/issues/1", "body": "Exact behavior", "title": "Task", "state": "OPEN"}
        self.comments = []

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.root, stderr=subprocess.PIPE)

    def publish(self, kind, record, supersedes=()):
        url = self.issue["url"] + "#issuecomment-" + str(len(self.comments) + 1)
        with patch.object(handoff.track, "run", return_value=url) as gh:
            result = handoff.record_v2(self.issue, self.comments, kind, record, supersedes=supersedes, cwd=self.root)
            if gh.called:
                self.comments.append({"id": len(self.comments) + 1, "html_url": url, "updated_at": "2026-01-01", "body": gh.call_args.args[-1]})
        return result

    def contract(self, supersedes=()):
        record = {"version": 2, "outcome": "Exact behavior", "requirements": [{"id": "R1", "expected": "Correct behavior", "required": True}],
                  "constraints": ["No push"], "exclusions": [], "decisions": [], "unresolved": [],
                  "checkpoint": packet.checkpoint(self.issue, self.comments)}
        result = self.publish("contract", record, supersedes)
        return result["metadata"]["record"]

    def plan(self, contract):
        record = {"version": 2, "contract_revision": contract["revision"], "steps": ["Implement and test"],
                  "check_manifest": {"version": 1, "checks": [{"id": "UNIT", "argv": [sys.executable, "-c", TEST_PROGRAM],
                       "kind": "test", "format": "unittest", "required": True}]},
                  "coverage": {"R1": {"checks": ["UNIT"]}}, "unresolved": []}
        result = self.publish("plan", record)
        return result["url"], record

    def verified(self):
        contract = self.contract()
        url, plan = self.plan(contract)
        verify.initialize(self.root, plan)
        run_id, result = verify.run_checks(self.root, self.issue, url, plan, contract)
        self.assertEqual(result["checks"][0]["status"], "pass")
        self.publish("verification", {"version": 2, "run_id": run_id})
        return contract, url, plan, run_id

    def review(self, contract, url, run_id, verdict="pass", findings=None, previous=None):
        return {"version": 2, "contract_revision": contract["revision"], "plan_url": url,
                "verification_run": run_id, "verdict": verdict, "findings": findings or [],
                **({"previous_review": previous} if previous else {})}

    def test_gate_pass_survives_commit_but_not_content_or_partial_index_changes(self):
        contract, url, plan, run_id = self.verified()
        review = self.publish("review", self.review(contract, url, run_id))
        self.assertTrue(handoff.v2_gate(self.issue, self.comments, url, cwd=self.root)["ready"])
        before = state.snapshot(self.root)["digest"]
        self.git("add", "."); self.git("commit", "-m", "feature")
        self.assertEqual(state.snapshot(self.root)["digest"], before)
        self.assertTrue(handoff.v2_gate(self.issue, self.comments, url, cwd=self.root)["ready"])
        (self.root / "api.txt").write_text("staged\n"); self.git("add", "api.txt")
        (self.root / "api.txt").write_text("base\n")
        with self.assertRaisesRegex(RuntimeError, "partial"):
            handoff.v2_gate(self.issue, self.comments, url, cwd=self.root)

    def test_old_comment_edits_and_deletions_cannot_hide_behind_checkpoint(self):
        self.comments.append({"id": 1, "html_url": self.issue["url"] + "#issuecomment-1", "body": "Human decision"})
        contract = self.contract()
        self.comments[0]["body"] = "Edited old decision"
        result = packet.build(self.issue, self.comments, "plan", cwd=self.root)
        self.assertTrue(result["blocked"])
        self.assertEqual(result["discussion_changes"]["comments"][0]["body"], "Edited old decision")
        with self.assertRaisesRegex(RuntimeError, "changed"):
            packet.contract_for(self.issue, self.comments)
        self.comments.pop(0)
        self.assertTrue(packet.pending(self.issue, self.comments, contract)["removed_comments"])

    def test_appended_text_to_v2_artifact_becomes_material_discussion(self):
        self.contract()
        self.comments[0]["body"] += "\nHuman correction after the marker"
        self.assertIsNone(packet.metadata(self.comments[0]))
        result = packet.build(self.issue, self.comments, "plan", cwd=self.root)
        self.assertEqual(result["mode"], "legacy")

    def test_current_contract_change_invalidates_old_plan(self):
        contract = self.contract()
        url, _ = self.plan(contract)
        old = self.comments[0]["html_url"]
        self.issue["body"] = "New required behavior"
        self.contract([old])
        with self.assertRaisesRegex(RuntimeError, "stale"):
            packet.plan_for(self.issue, self.comments, url)

    def test_issue_title_change_is_not_silently_ignored(self):
        self.contract()
        self.issue["title"] = "Changed requested outcome"
        with self.assertRaisesRegex(RuntimeError, "changed"):
            packet.contract_for(self.issue, self.comments)

    def test_missing_required_coverage_rejected(self):
        contract = self.contract()
        bad = {"version": 2, "contract_revision": contract["revision"], "steps": ["Code"],
               "check_manifest": {"version": 1, "checks": []}, "coverage": {}}
        with self.assertRaises(RuntimeError):
            self.publish("plan", bad)

    def test_reverting_plan_does_not_return_a_superseded_historical_url(self):
        contract = self.contract()
        first_url, original = self.plan(contract)
        revised = {**original, "steps": ["A different approved implementation path"]}
        second = self.publish("plan", revised, [first_url])
        third = self.publish("plan", original, [second["url"]])
        self.assertNotEqual(third["url"], first_url)
        self.assertEqual(packet.select(self.comments, "plan")["html_url"], third["url"])

    def test_skipped_tests_and_empty_execution_are_not_success(self):
        check = {"id": "T", "kind": "test", "format": "go-json", "required": True}
        skipped = '{"Test":"TestX","Action":"skip"}\n{"Action":"pass"}\n'
        self.assertNotEqual(verify.parse_result(check, 0, skipped, "")["status"], "pass")
        self.assertNotEqual(verify.parse_result(check, 0, '{"Action":"pass"}', "")["status"], "pass")
        self.assertNotEqual(verify.parse_result({**check, "format": "unittest"}, 0, "", "Ran 1 test in 0.1s\nOK (skipped=1)")["status"], "pass")

    def test_runner_results_and_logs_cannot_be_edited_into_a_pass(self):
        contract, url, plan, run_id = self.verified()
        result = verify.load_run(self.root, run_id)
        Path(result["checks"][0]["stdout_path"]).write_text("modified output")
        with self.assertRaisesRegex(RuntimeError, "log"):
            verify.readiness(self.root, self.issue, self.comments, url, run_id)

    def test_required_finding_cannot_disappear_or_become_optional(self):
        contract, url, plan, run_id = self.verified()
        finding = {"id": "F1", "expected": "Required behavior", "observed": "Missing case", "location": "api.txt:1",
                   "severity": "medium", "required": True, "status": "open"}
        prior = self.publish("review", self.review(contract, url, run_id, "changes_requested", [finding]))
        for findings in ([], [{**finding, "required": False}]):
            with self.assertRaises(RuntimeError):
                self.publish("review", self.review(contract, url, run_id, "pass", findings, prior["url"]), [prior["url"]])
        repaired = {**finding, "status": "resolved", "evidence": "UNIT passes; inspected source"}
        self.publish("review", self.review(contract, url, run_id, "pass", [repaired], prior["url"]), [prior["url"]])
        self.assertTrue(handoff.v2_gate(self.issue, self.comments, url, cwd=self.root)["ready"])

    def test_initial_review_does_not_replay_prior_review_but_fix_does(self):
        contract, url, plan, run_id = self.verified()
        self.publish("review", self.review(contract, url, run_id))
        first = packet.build(self.issue, self.comments, "review", cwd=self.root)
        fix = packet.build(self.issue, self.comments, "execute", cwd=self.root)
        self.assertNotIn("review", first)
        self.assertIn("review", fix)

    def test_explicit_reuse_and_invalidated_source(self):
        contract, url, plan, run_id = self.verified()
        reused_id, reused = verify.run_checks(self.root, self.issue, url, plan, contract, reuse=True)
        self.assertTrue(reused["checks"][0]["reused"])
        (self.root / "api.txt").write_text("new source\n")
        _, fresh = verify.run_checks(self.root, self.issue, url, plan, contract, reuse=True)
        self.assertFalse(fresh["checks"][0]["reused"])
        with self.assertRaisesRegex(RuntimeError, "stale"):
            verify.readiness(self.root, self.issue, self.comments, url, run_id)

    def test_repair_delta_points_to_real_diff_and_snapshot_is_read_only(self):
        old = state.snapshot(self.root)
        index = (self.root / ".git/index").read_bytes()
        (self.root / "api.txt").write_text("fixed\n")
        new = state.snapshot(self.root)
        delta = state.delta(old, new, self.root)
        self.assertEqual(delta["changed_files"], ["api.txt"])
        self.assertIn("+fixed", Path(delta["patch_file"]).read_text())
        self.assertEqual(index, (self.root / ".git/index").read_bytes())

    def test_state_directory_cannot_be_inside_source(self):
        with patch.dict(os.environ, {"OPENCODE_WORKFLOW_STATE": str(self.root / "bad-state")}):
            with self.assertRaisesRegex(RuntimeError, "outside"):
                state.snapshot(self.root)

    def test_unchanged_machine_observations_do_not_force_replanning(self):
        self.contract()
        prefix = "## Branch tracking\n\nBranch: `feature`\n\nTarget: `origin/main`\n\nAutomatic detection; sync requires an explicit request.\n\n<!-- opencode-track:register-feature -->"
        note = {"id": 2, "html_url": self.issue["url"] + "#issuecomment-2", "body": operational.wrap(prefix)}
        self.comments.append(note)
        self.assertTrue(operational.valid(note))
        packet.contract_for(self.issue, self.comments)
        note["body"] += "\nActually change the API"
        self.assertFalse(operational.valid(note))
        with self.assertRaises(RuntimeError):
            packet.contract_for(self.issue, self.comments)

    def test_untrusted_prose_cannot_hide_in_an_operational_envelope(self):
        note = {"html_url": self.issue["url"], "body": operational.wrap("Human requirement, not a machine branch observation")}
        self.assertFalse(operational.valid(note))

    def test_source_changes_during_checks_invalidate_the_receipt(self):
        contract = self.contract()
        url, plan = self.plan(contract)
        changed = copy.deepcopy(plan)
        changed["check_manifest"]["checks"][0]["argv"] = [sys.executable, "-c", "from pathlib import Path;Path('api.txt').write_text('changed')\n" + TEST_PROGRAM]
        # Deliberately revise the approved plan rather than silently changing a check.
        result = self.publish("plan", changed, [url])
        verify.initialize(self.root, changed)
        _, receipt = verify.run_checks(self.root, self.issue, result["url"], changed, contract)
        self.assertEqual(receipt["checks"][0]["status"], "source_changed")

    def test_declared_environment_changes_invalidate_reuse(self):
        contract = self.contract()
        url, plan = self.plan(contract)
        plan["check_manifest"]["checks"][0]["env_keys"] = ["WORKFLOW_TEST_MODE"]
        result = self.publish("plan", plan, [url])
        verify.initialize(self.root, plan)
        with patch.dict(os.environ, {"WORKFLOW_TEST_MODE": "one"}):
            run_id, _ = verify.run_checks(self.root, self.issue, result["url"], plan, contract)
        with patch.dict(os.environ, {"WORKFLOW_TEST_MODE": "two"}):
            with self.assertRaisesRegex(RuntimeError, "environment"):
                verify.readiness(self.root, self.issue, self.comments, result["url"], run_id)

    def test_declared_timeout_is_a_failed_check_not_success(self):
        stdout, stderr, code = verify.execute({"argv": [sys.executable, "-c", "import time;time.sleep(10)"], "timeout_seconds": .05}, self.root)
        self.assertEqual(code, 124)
        self.assertIn("timeout", stderr)

    def test_legacy_pass_is_not_v2_ready(self):
        self.comments.append({"id": 1, "html_url": self.issue["url"] + "#issuecomment-1",
            "body": 'Review pass\n<!-- opencode-workflow:v1 {"stage":"review","source":{"digest":"old"},"verdict":"pass"} -->'})
        with self.assertRaises(RuntimeError):
            handoff.v2_gate(self.issue, self.comments, self.issue["url"] + "#issuecomment-1", cwd=self.root)

    def test_new_failed_verification_cannot_be_hidden_by_old_passing_review(self):
        contract, url, plan, run_id = self.verified()
        previous = packet.select(self.comments, "verification")["html_url"]
        self.publish("review", self.review(contract, url, run_id))
        with patch.object(verify, "execute", return_value=("", "FAILED", 1)):
            failed, _ = verify.run_checks(self.root, self.issue, url, plan, contract)
        self.publish("verification", {"version": 2, "run_id": failed}, [previous])
        with self.assertRaisesRegex(RuntimeError, "current verification"):
            handoff.v2_gate(self.issue, self.comments, url, cwd=self.root)

    def test_compaction_retains_contract_but_not_superseded_research_bodies(self):
        contract = self.contract()
        first = {"version": 2, "contract_revision": contract["revision"], "facts": [
            {"id": "FACT1", "claim": "old investigation " * 1000, "locations": [{"path": "api.txt"}]}], "open_questions": []}
        old = self.publish("research", first)
        first["facts"][0]["claim"] = "Current fact"
        self.publish("research", first, [old["url"]])
        compact = packet.build(self.issue, self.comments, "plan", cwd=self.root)
        history = packet.build(self.issue, self.comments, "plan", history=True, cwd=self.root)
        self.assertNotIn("old investigation", json.dumps(compact))
        self.assertIn("old investigation", json.dumps(history))
        self.assertEqual(compact["contract"]["requirements"], contract["requirements"])
        self.assertLess(compact["context_bytes"], history["context_bytes"])
