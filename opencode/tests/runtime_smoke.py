#!/usr/bin/env python3
"""Explicit live-model profile/resource/patch-permission smoke; no GitHub writes.

Two tiny native command turns. A disposable worktree is outside the approved
temporary-artifact tree so a broad temp allow rule cannot invalidate the probe.
"""
import concurrent.futures
import importlib.util
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("runtime_launch", ROOT / "runtime/launch.py")
launch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launch)


def main():
    bundle = launch.build_bundle(ROOT)
    env = launch.environment(bundle, os.environ.get("OPENCODE_WORKFLOW_PROFILE"))
    cfg = json.loads(env["OPENCODE_CONFIG_CONTENT"])
    roles = {name: {key: value[key] for key in ("model", "variant")}
             for name, value in cfg["agent"].items()}
    cfg["agent"]["workflow-plan"]["prompt"] = "Configuration smoke only: follow the two apply_patch probes, then stop. No business workflow, GitHub, Bash, questions, or subagents."
    cfg["agent"]["workflow-execute"]["prompt"] = "Configuration smoke only: reply MODEL_READY. No tools, coding, GitHub or business workflow."
    cfg["command"]["permission-smoke"] = {"description": "Disposable permission probe", "agent": "workflow-plan",
        **roles["workflow-plan"], "subtask": True, "template": "$ARGUMENTS"}
    cfg["command"]["model-smoke"] = {"description": "Resolved execution profile probe", "agent": "workflow-execute",
        **roles["workflow-execute"], "subtask": True, "template": "Reply MODEL_READY only. No tools."}
    env["OPENCODE_CONFIG_CONTENT"] = json.dumps(cfg)
    artifact = Path(tempfile.gettempdir()) / "opencode" / ("workflow-permission-" + uuid.uuid4().hex + ".md")
    artifact.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="runtime-smoke-", dir=ROOT / "tests") as tmp:
        directory = Path(tmp)
        subprocess.run(["git", "init", "-q"], cwd=directory, check=True)
        sentinel = directory / "application.txt"
        sentinel.write_text("UNCHANGED\n")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        def api(method, path, data=None, timeout=180):
            query = urllib.parse.urlencode({"directory": str(directory)})
            request = urllib.request.Request(f"http://127.0.0.1:{port}" + path + "?" + query,
                data=json.dumps(data).encode() if data is not None else None,
                headers={"Content-Type": "application/json"}, method=method)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
                return json.loads(raw) if raw else None
        with (directory / "server.log").open("w") as log:
            process = subprocess.Popen(["opencode", "serve", "--pure", "--hostname", "127.0.0.1", "--port", str(port)],
                cwd=directory, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                for _ in range(100):
                    if process.poll() is not None:
                        raise RuntimeError((directory / "server.log").read_text())
                    try:
                        api("GET", "/global/health", timeout=1)
                        break
                    except Exception:
                        time.sleep(.2)
                commands = {x["name"]: x for x in api("GET", "/command")}
                agents = {x["name"]: x for x in api("GET", "/agent")}
                resolved = api("GET", "/config")
                for stage in launch.STAGES:
                    expected = roles["workflow-" + stage]
                    assert commands[stage]["model"] == expected["model"]
                    assert resolved["command"][stage]["variant"] == expected["variant"]
                    assert agents["workflow-" + stage]["variant"] == expected["variant"]
                    assert commands[stage]["subtask"] is True
                    assert agents["workflow-" + stage]["model"]["modelID"] == expected["model"].split("/", 1)[1]
                skills = {x["name"]: x for x in api("GET", "/skill")}
                aliases = launch.validate_bundle(bundle)["skill_aliases"]
                assert all(bundle in Path(skills[aliases["workflow-" + s]]["location"]).resolve().parents for s in launch.STAGES), "A live skill leaked into pinned workflow"
                providers = {p["id"]: p["models"] for p in api("GET", "/provider")["all"]}
                for settings in roles.values():
                    provider, model = settings["model"].split("/", 1)
                    assert model in providers[provider]
                    if settings["variant"]:
                        assert settings["variant"] in providers[provider][model]["variants"]
                parent = api("POST", "/session", {"title": "Disposable workflow v2 smoke"})["id"]
                results = {}
                for name in ("permission-smoke", "model-smoke"):
                    before = {c["id"] for c in api("GET", f"/session/{parent}/children")}
                    prompt = (f"First, in its own apply_patch call, create {artifact} containing TEMP_ALLOWED. "
                              f"Then in a separate apply_patch call attempt to replace UNCHANGED in {sentinel} with DENIED_PROBE. "
                              "The second call is expected to be denied by your read-only permissions. This disposable probe is authorized, "
                              "but do not bypass denial, request permission, use another tool, or write anywhere else. Return a short result.")
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                        future = pool.submit(api, "POST", f"/session/{parent}/command", {"command": name, "agent": "workflow", "arguments": prompt})
                        while not future.done():
                            if api("GET", "/question") or api("GET", "/permission"):
                                api("POST", f"/session/{parent}/abort", {})
                                raise RuntimeError("Unexpected approval request during fixed-permission smoke")
                            time.sleep(.4)
                        future.result()
                    child = [c for c in api("GET", f"/session/{parent}/children") if c["id"] not in before]
                    assert len(child) == 1
                    messages = api("GET", f"/session/{child[0]['id']}/message")
                    paid = [m["info"] for m in messages if m["info"]["role"] == "assistant" and m["info"].get("tokens", {}).get("total", 0)]
                    selected = roles["workflow-plan" if name == "permission-smoke" else "workflow-execute"]
                    expected = (selected["model"].split("/", 1)[1], selected["variant"])
                    assert paid and all((m["modelID"], m.get("variant") or "") == expected for m in paid)
                    if name == "permission-smoke":
                        assert artifact.exists() and "TEMP_ALLOWED" in artifact.read_text()
                        assert sentinel.read_text() == "UNCHANGED\n"
                        denied = [p for m in messages for p in m["parts"] if p.get("type") == "tool" and p.get("state", {}).get("status") == "error"]
                        assert any("application.txt" in json.dumps(p.get("state", {}).get("input", {})) for p in denied), "No actual denied patch recorded"
                    results[name] = {"child": child[0]["id"], "model": expected[0], "variant": expected[1],
                                     "reported_tokens": sum(m["tokens"]["total"] for m in paid)}
                launch.validate_bundle(bundle)
                print(json.dumps({"outcome": "pass", "pinned_revision": bundle.name, "results": results,
                    "temporary_patch_allowed": True, "application_patch_denied": True,
                    "all_six_bindings_and_skill_locations": "pass"}, indent=2))
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(10)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                artifact.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
