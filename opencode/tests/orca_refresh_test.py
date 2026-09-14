import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("refresh_checkout", Path(__file__).resolve().parents[1] / "orca/refresh_checkout.py")
refresh = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(refresh)


class RefreshTest(unittest.TestCase):
    def git(self, path, *args):
        return subprocess.check_output(["git", "-C", str(path), *args], text=True, stderr=subprocess.DEVNULL).strip()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.remote, self.seed, self.checkout = (root / p for p in ("remote.git", "seed", "checkout"))
        subprocess.run(["git", "init", "--bare", str(self.remote)], check=True, capture_output=True)
        subprocess.run(["git", "init", "-b", "main", str(self.seed)], check=True, capture_output=True)
        (self.seed / "tracked.txt").write_text("original\n")
        self.commit(self.seed)
        self.git(self.seed, "remote", "add", "origin", str(self.remote))
        self.git(self.seed, "push", "-u", "origin", "main")
        subprocess.run(["git", "clone", "-b", "main", str(self.remote), str(self.checkout)], check=True, capture_output=True)

    def commit(self, path):
        self.git(path, "add", ".")
        self.git(path, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "fixture")

    def run_refresh(self, apply=True):
        return refresh.refresh(self.checkout, str(self.remote), apply=apply)

    def test_refresh_discards_tracked_edits_and_preserves_untracked_env(self):
        (self.seed / "tracked.txt").write_text("upstream\n")
        self.commit(self.seed)
        self.git(self.seed, "push")
        (self.checkout / "tracked.txt").write_text("discard this\n")
        (self.checkout / ".env").write_text("local fixture\n")
        result = self.run_refresh()
        self.assertEqual(result["head"], self.git(self.seed, "rev-parse", "HEAD"))
        self.assertEqual(result["discardedTrackedPaths"], ["tracked.txt"])
        self.assertEqual((self.checkout / "tracked.txt").read_text(), "upstream\n")
        self.assertEqual((self.checkout / ".env").read_text(), "local fixture\n")

    def test_precheck_is_read_only(self):
        (self.checkout / "tracked.txt").write_text("retain\n")
        self.assertEqual(self.run_refresh(apply=False)["outcome"], "precheck_passed")
        self.assertEqual((self.checkout / "tracked.txt").read_text(), "retain\n")
        self.assertFalse((self.checkout / ".git/opencode-refresh.lock").exists())

    def test_staged_work_is_preserved(self):
        (self.checkout / "tracked.txt").write_text("staged\n")
        self.git(self.checkout, "add", "tracked.txt")
        with self.assertRaisesRegex(RuntimeError, "Staged changes"):
            self.run_refresh()
        self.assertEqual(self.git(self.checkout, "show", ":tracked.txt"), "staged")

    def test_local_commits_and_unstaged_work_are_preserved(self):
        (self.checkout / "tracked.txt").write_text("local commit\n")
        self.commit(self.checkout)
        head = self.git(self.checkout, "rev-parse", "HEAD")
        (self.checkout / "tracked.txt").write_text("local edit\n")
        with self.assertRaisesRegex(RuntimeError, "Local-only commits"):
            self.run_refresh()
        self.assertEqual(self.git(self.checkout, "rev-parse", "HEAD"), head)
        self.assertEqual((self.checkout / "tracked.txt").read_text(), "local edit\n")

    def test_wrong_branch_or_remote_is_refused(self):
        with self.assertRaisesRegex(RuntimeError, "origin differs"):
            refresh.refresh(self.checkout, "wrong", apply=True)
        self.git(self.checkout, "switch", "-c", "feature")
        with self.assertRaisesRegex(RuntimeError, "configured branch"):
            self.run_refresh()

    def test_operation_in_progress_is_refused(self):
        (self.checkout / ".git/MERGE_HEAD").write_text(self.git(self.checkout, "rev-parse", "HEAD"))
        with self.assertRaisesRegex(RuntimeError, "Unfinished Git operation"):
            self.run_refresh()

    def test_untracked_collision_is_never_deleted(self):
        (self.seed / "new.txt").write_text("upstream\n")
        self.commit(self.seed)
        self.git(self.seed, "push")
        (self.checkout / "new.txt").write_text("local untracked\n")
        with self.assertRaisesRegex(RuntimeError, "fast-forward failed"):
            self.run_refresh()
        self.assertEqual((self.checkout / "new.txt").read_text(), "local untracked\n")

    def test_ignored_env_collision_is_never_overwritten(self):
        (self.checkout / ".git/info/exclude").write_text(".env\n")
        (self.checkout / ".env").write_text("local environment\n")
        (self.seed / ".env").write_text("upstream environment\n")
        self.commit(self.seed)
        self.git(self.seed, "push")
        with self.assertRaisesRegex(RuntimeError, "fast-forward failed"):
            self.run_refresh()
        self.assertEqual((self.checkout / ".env").read_text(), "local environment\n")


if __name__ == "__main__":
    unittest.main()
