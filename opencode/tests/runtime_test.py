"""Snapshot/profile behavior without paid models or changing real HOME."""
import importlib.util
import json
import re
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("workflow_launch", ROOT / "runtime/launch.py")
launch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launch)


class RuntimeTest(unittest.TestCase):
    def test_snapshot_isolated_from_live_edits_and_idempotent(self):
        with tempfile.TemporaryDirectory(prefix="workflow snapshot space ") as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            (source / "profiles.json").write_bytes((ROOT / "profiles.json").read_bytes())
            (source / "tracking").mkdir()
            target = source / "tracking/procedure.md"
            target.write_text("Run python3 {{WORKFLOW_ROOT}}/tracking/handoff.py packet\n")
            bundle = launch.build_bundle(source, Path(tmp) / "state")
            content = (bundle / "opencode/tracking/procedure.md").read_text()
            self.assertIn('python3 "' + str(bundle), content)
            self.assertNotIn("{{WORKFLOW_ROOT}}", content)
            self.assertEqual(launch.build_bundle(source, Path(tmp) / "state"), bundle)
            target.write_text("new live procedure\n")
            self.assertEqual((bundle / "opencode/tracking/procedure.md").read_text(), content)
            self.assertNotEqual(launch.build_bundle(source, Path(tmp) / "state"), bundle)
            (bundle / "opencode/tracking/procedure.md").write_text("tampered")
            with self.assertRaisesRegex(RuntimeError, "changed"):
                launch.validate_bundle(bundle)

    def test_profiles_route_both_layers_and_preserve_user_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = launch.build_bundle(ROOT, Path(tmp))
            env = {"HOME": "/real/home", "GH_TOKEN": "private-fixture-token", "OPENCODE_CONFIG_CONTENT": json.dumps({"model": "local/keep", "agent": {"custom": {"description": "keep"}}})}
            for profile, model, effort in (("balanced", "openai/gpt-5.6-sol", "xhigh"),
                                          ("baseline", "openai/gpt-5.6-sol", "medium"),
                                          ("astra-high", "openai/gpt-6-astra", "high")):
                actual = launch.environment(bundle, profile, env)
                cfg = json.loads(actual["OPENCODE_CONFIG_CONTENT"])
                self.assertEqual(actual["HOME"], env["HOME"])
                self.assertEqual(actual["GH_TOKEN"], env["GH_TOKEN"])
                self.assertEqual(cfg["agent"]["custom"]["description"], "keep")
                self.assertEqual(cfg["model"], "local/keep")
                for item in (cfg["agent"]["workflow-execute"], cfg["command"]["execute"]):
                    self.assertEqual(item["model"], model)
                    self.assertEqual(item["variant"], effort)
                self.assertTrue(cfg["command"]["execute"]["subtask"])
                self.assertEqual(cfg["command"]["review"]["variant"], "medium")
            self.assertNotIn("private-fixture-token", (bundle / "manifest.json").read_text())
            with self.assertRaises(RuntimeError):
                launch.profile(bundle / "opencode", "missing")
            with self.assertRaisesRegex(RuntimeError, "does not exist"):
                launch.environment(bundle, environ={"OPENCODE_CONFIG_DIR": "/unrelated/custom"})

    def test_orca_hooks_and_custom_agents_are_preserved_without_home_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = launch.build_bundle(ROOT, Path(tmp) / "state")
            custom = Path(tmp) / "orca config"
            (custom / "plugins").mkdir(parents=True)
            (custom / "plugins/hook.js").write_text("export default async()=>({})")
            (custom / "agents").mkdir()
            (custom / "agents/vendor.md").write_text("vendor agent")
            env = launch.environment(bundle, environ={"HOME": "/real/home", "OPENCODE_CONFIG_DIR": str(custom)})
            bridge = Path(env["OPENCODE_CONFIG_DIR"])
            self.assertEqual((bridge / "plugins/hook.js").resolve(), (custom / "plugins/hook.js").resolve())
            self.assertEqual((bridge / "agents/vendor.md").resolve(), (custom / "agents/vendor.md").resolve())
            self.assertEqual(launch.environment(bundle, environ=env)["OPENCODE_CONFIG_DIR"], str(bridge))
            self.assertEqual(env["HOME"], "/real/home")
            (custom / "agents/workflow-execute.md").write_text("conflicting custom worker")
            with self.assertRaisesRegex(RuntimeError, "conflicts"):
                launch.environment(bundle, environ={"OPENCODE_CONFIG_DIR": str(custom)})

    def test_direct_launch_fallbacks_match_default_profile(self):
        _, roles = launch.profile(ROOT)
        for role, settings in roles.items():
            paths = [ROOT / "agents" / (role + ".md")]
            if role.startswith("workflow-"):
                paths.append(ROOT / "commands" / (role.removeprefix("workflow-") + ".md"))
            for path in paths:
                text = path.read_text().split("---", 2)[1]
                for key, value in settings.items():
                    self.assertEqual(re.search(r"^" + key + r":\s*(.+)$", text, re.M)[1], value)
