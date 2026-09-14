"""Generic distribution, fresh-home installation and process-boundary checks."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("setup_launch", ROOT / "opencode/runtime/launch.py")
launch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launch)


class DistributionTest(unittest.TestCase):
    def test_source_syntax_and_whitespace_including_new_files(self):
        for path in [ROOT / "workflow.py", *(ROOT / "opencode").rglob("*")]:
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            text = path.read_text()
            with self.subTest(path=str(path.relative_to(ROOT))):
                for line in text.splitlines():
                    self.assertEqual(line, line.rstrip(), "trailing whitespace")
                if path.suffix == ".py":
                    compile(text, str(path), "exec")
                elif path.suffix == ".sh":
                    result = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    if "scripts" in path.parts:
                        self.assertTrue(path.stat().st_mode & 0o111, "script lost executable mode")

    def test_public_files_have_no_legacy_identity_or_home_paths(self):
        # Hashes of retired identity/project tokens: don't reintroduce the actual
        # private identifiers into a public test fixture just to prohibit them.
        forbidden = {
            "b33fe50755c0297398165724732643c122a9c6f92e4658e9d0bb0497d813c285",
            "f40cc1299629259447e388440ce62167fc6caa3b9dc387640bf2e9621293a73e",
            "04b58c865eb0422452d0ef81a1d6b884b63d06720184c947b1d838bd3458e9d9",
            "95ca85ed435595937ab9a0da1fac322f8bfd54506363e97ab9df7f2e8637c6b1",
        }
        for path in ROOT.rglob("*"):
            if any(p in {".git", "__pycache__", ".venv"} for p in path.relative_to(ROOT).parts):
                continue
            if not path.is_file():
                continue
            text = path.read_text()
            with self.subTest(path=str(path.relative_to(ROOT))):
                words = re.findall(r"[a-z0-9]+", text.lower())
                self.assertFalse({hashlib.sha256(w.encode()).hexdigest() for w in words} & forbidden)
                self.assertNotRegex(text, r"/" + r"(?:Users|home)/[a-zA-Z][a-zA-Z0-9_-]*/")

    def test_templates_are_self_contained_and_licenses_survive_packaging(self):
        with tempfile.TemporaryDirectory(prefix="resource space ") as tmp:
            bundle = launch.build_bundle(ROOT / "opencode", Path(tmp))
            self.assertEqual((bundle / "opencode/LICENSE").read_bytes(), (ROOT / "LICENSE").read_bytes())
            self.assertEqual((bundle / "opencode/tracking/LICENSE.agentic").read_bytes(),
                             (ROOT / "opencode/tracking/LICENSE.agentic").read_bytes())
            for path in (ROOT / "opencode").rglob("*.md"):
                if "tests" in path.parts:
                    continue
                text = path.read_text()
                for relative in re.findall(r"\{\{WORKFLOW_ROOT\}\}(/[\w/.-]+)", text):
                    self.assertTrue((ROOT / "opencode" / relative.lstrip("/")).exists(), (path, relative))
                if path.name == "SKILL.md":
                    front = text.split("---", 2)[1]
                    self.assertRegex(front, r"(?m)^description: .+", path)
                    self.assertEqual(re.search(r"(?m)^name: (.+)$", front)[1], path.parent.name)
            for path in (bundle / "opencode").rglob("*.md"):
                self.assertNotIn("{{WORKFLOW_ROOT}}", path.read_text(), path)
                self.assertNotIn("~/.config/opencode/skills/", path.read_text(), path)
                self.assertNotIn("AskUserQuestion", path.read_text(), path)
            # Execute a resolved read-only Git helper through the actual emitted
            # command path, with no global skill catalog and a spaced state path.
            skill = bundle / "opencode/skills/git/git-commit/SKILL.md"
            commands = re.findall(r'bash "([^"\n]+/analyze-changes.sh)"', skill.read_text())
            self.assertTrue(commands)
            repo = Path(tmp) / "application"
            repo.mkdir()
            subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
            (repo / "file.txt").write_text("user work\n")
            result = subprocess.run(["bash", commands[0]], cwd=repo, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((repo / "file.txt").read_text(), "user work\n")


class SetupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="workflow install space ")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith(("OPENCODE_", "XDG_", "PYTHONPATH"))}
        self.env.update(HOME=str(self.home), XDG_CONFIG_HOME=str(self.home / "config"),
                        OPENCODE_WORKFLOW_STATE=str(self.home / "state"), PYTHONDONTWRITEBYTECODE="1")
        self.cli = ROOT / "workflow.py"

    def run_cli(self, *args, expected=0):
        result = subprocess.run([sys.executable, "-B", str(self.cli), *args], env=self.env,
                                cwd=self.root, capture_output=True, text=True)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def test_relocated_install_launch_arguments_status_and_local_settings(self):
        checkout = self.root / "arbitrary checkout"
        checkout.mkdir()
        shutil.copy2(ROOT / "workflow.py", checkout)
        shutil.copy2(ROOT / "LICENSE", checkout)
        shutil.copytree(ROOT / "opencode", checkout / "opencode", ignore=shutil.ignore_patterns("__pycache__"))
        self.cli = checkout / "workflow.py"
        config = self.home / "config/opencode"
        config.mkdir(parents=True)
        native = config / "opencode.jsonc"
        native.write_text('// keep user settings\n{"model":"local/keep"}\n')
        original = native.read_bytes()
        skills = self.home / "private skills/my-skill"
        skills.mkdir(parents=True)
        (skills / "SKILL.md").write_text('---\nname: my-skill\ndescription: Private fixture\n---\nSECRET_BODY\n')
        bindir = self.root / "bin directory"
        self.run_cli("install", "--bin-dir", str(bindir), "--model", "local/test-model",
                     "--skills-path", str(skills.parent))
        wrapper = bindir / "opencode-workflow"
        settings = self.home / "config/opencode-workflow/config.json"
        before = settings.read_bytes()
        self.assertEqual(settings.stat().st_mode & 0o777, 0o600)
        self.assertEqual(wrapper.stat().st_mode & 0o777, 0o755)
        self.assertNotIn("tracking", json.loads(before))
        self.run_cli("install", "--bin-dir", str(bindir), "--model", "local/new", expected=1)
        self.assertEqual(settings.read_bytes(), before)
        fake = bindir / "opencode"
        fake.write_text('#!' + sys.executable + '\nimport json,os,sys\n'
                        'c=json.loads(os.environ["OPENCODE_CONFIG_CONTENT"])\n'
                        'print(json.dumps({"args":sys.argv[1:],"cwd":os.getcwd(),"config":c}))\n'
                        'sys.exit(23)\n')
        fake.chmod(0o755)
        self.env["PATH"] = str(bindir) + os.pathsep + self.env["PATH"]
        result = subprocess.run([str(wrapper), "launch", "--", "argument with spaces"],
                                env=self.env, cwd=self.root, text=True, capture_output=True)
        self.assertEqual(result.returncode, 23, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["args"], ["argument with spaces"])
        self.assertEqual(Path(output["cwd"]).resolve(), self.root.resolve())
        cfg = output["config"]
        for agent in cfg["agent"].values():
            self.assertEqual(agent["model"], "local/test-model")
        self.assertIn("my-skill", cfg["command"])
        self.assertNotIn("SECRET_BODY", result.stdout)
        self.assertEqual(native.read_bytes(), original)
        metadata = json.loads(self.run_cli("prepare").stdout)
        resources = Path(metadata["OPENCODE_WORKFLOW_ROOT"])
        self.assertNotIn("local/test-model", (resources / "profiles.json").read_text())
        self.assertFalse(any(p.name == "my-skill" for p in resources.rglob("*")))
        self.assertEqual(json.loads(self.run_cli("doctor").stdout)["configuration"], "pass")

    def test_uninstall_round_trip_preserves_settings_and_is_repeatable(self):
        for bindir in (self.home / ".local/bin", self.root / "custom bin"):
            with self.subTest(bindir=bindir):
                args = [] if bindir == self.home / ".local/bin" else ["--bin-dir", str(bindir)]
                self.run_cli("install", "--launcher-only", *args)
                sentinel = self.home / "state/evidence.txt"
                sentinel.parent.mkdir(exist_ok=True)
                sentinel.write_text("private evidence")
                self.run_cli("uninstall", *args)
                self.assertFalse((bindir / "opencode-workflow").exists())
                self.assertEqual(sentinel.read_text(), "private evidence")
                self.run_cli("uninstall", *args)
                self.run_cli("install", "--launcher-only", *args)

    def test_uninstall_preserves_unrecognized_launchers(self):
        bindir = self.root / "bin"
        self.run_cli("install", "--launcher-only", "--bin-dir", str(bindir))
        wrapper = bindir / "opencode-workflow"
        original = wrapper.read_bytes()
        for content in (b"user executable", original + b"# edited\n",
                        original.replace(str(ROOT).encode(), b"/different-checkout")):
            wrapper.write_bytes(content)
            self.run_cli("uninstall", "--bin-dir", str(bindir), expected=1)
            self.assertEqual(wrapper.read_bytes(), content)
        wrapper.unlink()
        destination = self.root / "other launcher"
        destination.write_bytes(original)
        wrapper.symlink_to(destination)
        self.run_cli("uninstall", "--bin-dir", str(bindir), expected=1)
        self.assertTrue(wrapper.is_symlink())
        self.assertEqual(destination.read_bytes(), original)
        destination.unlink()
        self.run_cli("uninstall", "--bin-dir", str(bindir), expected=1)
        self.assertTrue(wrapper.is_symlink())
        wrapper.unlink()
        wrapper.mkdir()
        self.run_cli("uninstall", "--bin-dir", str(bindir), expected=1)
        self.assertTrue(wrapper.is_dir())

    def test_invalid_setup_and_existing_profile_are_preserved(self):
        config = self.home / "config/opencode-workflow/config.json"
        for args in [("--project-owner", "example"), ("--project-owner", "example", "--project-number", "0"),
                     ("--model", "invalid"), ("--skills-path", str(self.root / "missing"))]:
            self.run_cli("setup", *args, expected=1)
            self.assertFalse(config.exists())
        config.parent.mkdir(parents=True)
        models = config.parent / "profiles.json"
        models.write_text("user-owned")
        self.run_cli("setup", "--model", "local/test", expected=1)
        self.assertEqual(models.read_text(), "user-owned")
        self.assertFalse(config.exists())

    def test_alternate_settings_path_board_and_launcher_only(self):
        config = self.root / "settings space/custom.json"
        self.env["OPENCODE_PRIVATE_CONFIG"] = str(config)
        self.run_cli("setup", "--project-owner", "example-org", "--project-number", "7")
        self.assertEqual(json.loads(config.read_text())["tracking"], {"owner": "example-org", "number": 7})
        self.run_cli("install", "--launcher-only", "--bin-dir", str(self.root / "bin"))
        self.run_cli("prepare")
        self.run_cli("launch", "--profile", "missing", expected=1)


if __name__ == "__main__":
    unittest.main()
