#!/usr/bin/env python3
"""Run approved repository checks and retain private, content-bound evidence.

Commands run only through an explicit `run --plan URL` invocation, never while
loading an issue/context. Check definitions are frozen in the identified plan.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time

import packet
import workflow_state as state

MANIFEST = ".opencode/workflow/checks.json"


def expected_manifest(plan):
    return plan["check_manifest"]


def validate_manifest(manifest):
    packet.require(isinstance(manifest, dict) and type(manifest.get("version")) is int and manifest["version"] == 1, "Check manifest requires version: 1")
    checks = packet.identified(manifest.get("checks"), "check")
    for check in checks.values():
        packet.strings(check.get("argv"), "argv")
        packet.require(bool(check["argv"]), "Check argv cannot be empty")
        packet.require(check.get("kind") in ("test", "compile", "lint", "static"), "Invalid check kind")
        packet.require(check.get("format", "exit") in ("exit", "go-json", "unittest", "script"), "Unsupported check format")
        packet.require(check["kind"] != "test" or check.get("format") in ("go-json", "unittest", "script"),
                       "Behavioral tests need parsed results, not exit-only proof")
        if check.get("format") == "script":
            packet.text(check.get("success_pattern"), "assertion-script success_pattern")
            re.compile(check["success_pattern"])
            re.compile(check.get("skip_pattern", r"(?im)^\s*SKIP\b"))
        packet.require(type(check.get("required")) is bool, "Each check must declare required true/false")
        packet.require(type(check.get("allow_skips", False)) is bool, "allow_skips must be boolean")
        packet.strings(check.get("required_tests", []), "required_tests")
        packet.require(not (check["required"] and check.get("allow_skips")) or bool(check.get("required_tests")),
                       "A required check allowing optional skips must name its mandatory tests")
        packet.require(not check.get("required_tests") or check.get("format") == "go-json", "Named required_tests need go-json")
        packet.strings(check.get("env_keys", []), "env_keys")
        env = check.get("env", {})
        packet.require(isinstance(env, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in env.items()), "env must be non-secret string configuration")
        packet.require(not any(re.search(r"token|password|secret|api.?key", k, re.I) for k in env), "Do not store credentials in a published check definition")
        timeout = check.get("timeout_seconds", 1800)
        packet.require(type(timeout) in (int, float) and math.isfinite(timeout) and timeout > 0, "timeout_seconds must be finite and positive")
        cwd = check.get("cwd", ".")
        packet.require(isinstance(cwd, str) and not Path(cwd).is_absolute() and ".." not in Path(cwd).parts, "Check cwd must be repository-relative")
    return manifest


def approved_plan(issue, comments, url):
    _, meta, contract = packet.plan_for(issue, comments, url)
    return meta["record"], contract


def initialize(root, plan):
    destination = state.confined(root, MANIFEST)
    expected = expected_manifest(plan)
    if destination.exists():
        if json.loads(destination.read_text()) != expected:
            raise RuntimeError("Existing repository check manifest differs; preserve it and revise/reconcile the plan explicitly")
        return destination
    state.save(destination, expected)
    return destination


def parse_result(spec, code, stdout, stderr):
    result = {"status": "pass" if code == 0 else "fail", "tests": {}, "skips": [], "test_count": None}
    form = spec.get("format", "exit")
    if form == "go-json":
        events = []
        try:
            events = [json.loads(line) for line in stdout.splitlines() if line.strip()]
        except ValueError:
            result["status"] = "unverified"
        for event in events:
            if event.get("Test") and event.get("Action") in ("pass", "fail", "skip"):
                result["tests"][event["Test"]] = event["Action"]
        result["skips"] = [name for name, outcome in result["tests"].items() if outcome == "skip"]
        result["test_count"] = len(result["tests"])
        if spec["kind"] == "test" and not any(x == "pass" for x in result["tests"].values()):
            result["status"] = "unverified"
        if any(x == "fail" for x in result["tests"].values()):
            result["status"] = "fail"
    elif form == "unittest":
        combined = stdout + "\n" + stderr
        match = re.search(r"Ran (\d+) tests? in", combined)
        result["test_count"] = int(match[1]) if match else None
        skip = re.search(r"OK \(skipped=(\d+)\)", combined)
        result["skips"] = ["unittest skipped count: " + skip[1]] if skip and int(skip[1]) else []
        if not match or int(match[1]) == 0 or not re.search(r"^OK(?:\s|$)", combined, re.M):
            result["status"] = "unverified" if code == 0 else "fail"
    elif form == "script":
        combined = stdout + "\n" + stderr
        result["success_markers"] = len(re.findall(spec["success_pattern"], combined, re.M))
        result["skips"] = [m.group(0) for m in re.finditer(spec.get("skip_pattern", r"(?im)^\s*SKIP\b"), combined)]
        if not result["success_markers"] and code == 0:
            result["status"] = "unverified"
    required = spec.get("required_tests", [])
    if any(result["tests"].get(name) != "pass" for name in required):
        result["status"] = "unverified"
    if result["skips"] and not spec.get("allow_skips", False):
        result["status"] = "unverified"
    return result


def environment_fingerprint(spec):
    # Values never leave this function. Include declared relevant environment,
    # conventional toolchain knobs, and the actual executable bytes when available.
    env = {**os.environ, **spec.get("env", {})}
    keys = {"PATH", "LANG", "LC_ALL", "TZ", "GOOS", "GOARCH", "CGO_ENABLED", *spec.get("env_keys", [])}
    binary = shutil.which(spec["argv"][0], path=env.get("PATH"))
    executable = state.file_hash(Path(binary)) if binary and Path(binary).is_file() else None
    return state.digest({"values": {k: env.get(k) for k in sorted(keys)}, "executable": executable})


def execute(spec, cwd):
    process = None
    try:
        process = subprocess.Popen(spec["argv"], cwd=cwd, env={**os.environ, **spec.get("env", {})},
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=os.name == "posix")
        stdout, stderr = process.communicate(timeout=spec.get("timeout_seconds", 1800))
        return stdout, stderr, process.returncode
    except (subprocess.TimeoutExpired, KeyboardInterrupt) as error:
        if process is not None:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            stdout, stderr = process.communicate()
        else:
            stdout, stderr = "", ""
        cancelled = isinstance(error, KeyboardInterrupt)
        return stdout, stderr + ("\nCheck cancelled" if cancelled else "\nCheck exceeded its declared timeout"), 130 if cancelled else 124
    except OSError as error:
        return "", str(error), 127


def load_run(root, run_id):
    if not re.fullmatch(r"[0-9a-f]{64}", str(run_id)):
        raise RuntimeError("Invalid verification run ID")
    path = state.storage(root) / "runs" / (run_id + ".json")
    try:
        result = json.loads(path.read_text())
    except FileNotFoundError:
        raise RuntimeError("Verification evidence unavailable on this machine; rerun approved checks")
    if state.digest(result) != run_id:
        raise RuntimeError("Verification record was modified")
    for check in result["checks"]:
        for key in ("stdout", "stderr"):
            log = Path(check[key + "_path"])
            if state.storage(root).resolve() not in log.resolve().parents or not log.is_file() or state.file_hash(log) != check[key + "_sha256"]:
                raise RuntimeError("Verification log missing or modified")
    return result


def readiness(root, issue, comments, plan_url, run_id, source=None):
    plan, contract = approved_plan(issue, comments, plan_url)
    result = load_run(root, run_id)
    if result.get("verifier_sha256") != state.file_hash(Path(__file__)):
        raise RuntimeError("Verifier implementation changed; rerun approved checks")
    source = source or state.snapshot(root)
    if result["source"]["digest"] != source["digest"] or result["contract_revision"] != contract["revision"]:
        raise RuntimeError("Verification source/contract is stale")
    if result["issue"] != issue["url"] or result["plan_url"] != plan_url or result["plan_digest"] != state.digest(plan):
        raise RuntimeError("Verification does not apply to this exact plan")
    manifest = state.confined(root, MANIFEST)
    if not manifest.exists() or json.loads(manifest.read_text()) != expected_manifest(plan):
        raise RuntimeError("Repository check definitions changed since plan approval")
    actual = {x["id"]: x for x in result["checks"]}
    for spec in plan["check_manifest"]["checks"]:
        check = actual.get(spec["id"])
        if not check or check["spec_digest"] != state.digest(spec):
            raise RuntimeError("Missing or changed check: " + spec["id"])
        if check["environment_fingerprint"] != environment_fingerprint(spec):
            raise RuntimeError("Relevant environment/toolchain changed: " + spec["id"])
        if spec.get("required", True) and check["status"] != "pass":
            raise RuntimeError("Required check did not pass: " + spec["id"] + " (" + check["status"] + ")")
    return result


def run_checks(root, issue, plan_url, plan, contract, reuse=False):
    destination = state.confined(root, MANIFEST)
    if not destination.exists() or json.loads(destination.read_text()) != expected_manifest(plan):
        raise RuntimeError("Initialize/reconcile the repository check manifest from the approved plan before running")
    source = state.snapshot(root)
    started = time.time()
    log_root = state.storage(root) / "logs"
    log_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    log_dir = Path(tempfile.mkdtemp(prefix="checks-", dir=log_root))
    verifier_hash = state.file_hash(Path(__file__))
    result = {"version": 2, "verifier_sha256": verifier_hash,
              "workflow_revision": os.environ.get("OPENCODE_WORKFLOW_REVISION"),
              "issue": issue["url"], "plan_url": plan_url, "plan_digest": state.digest(plan),
              "contract_revision": contract["revision"], "source": source, "start": started, "checks": []}
    old = []
    if reuse:
        for path in sorted((state.storage(root) / "runs").glob("*.json"), reverse=True):
            try:
                item = load_run(root, path.stem)
                if (item.get("verifier_sha256") == verifier_hash and item["source"]["digest"] == source["digest"]
                        and item["contract_revision"] == contract["revision"]):
                    old.extend(item["checks"])
            except (RuntimeError, OSError, ValueError, KeyError):
                continue
    for spec in plan["check_manifest"]["checks"]:
        fingerprint = environment_fingerprint(spec)
        prior = next((x for x in old if x["spec_digest"] == state.digest(spec) and x["environment_fingerprint"] == fingerprint and x["status"] == "pass"), None)
        if prior:
            result["checks"].append({**prior, "reused": True})
            continue
        cwd = root if spec.get("cwd", ".") == "." else state.confined(root, spec["cwd"])
        if not cwd.is_dir():
            raise RuntimeError("Check cwd is missing")
        before = state.snapshot(root)
        begin = time.time()
        stdout, stderr, code = execute(spec, cwd)
        parsed = parse_result(spec, code, stdout, stderr)
        after = state.snapshot(root)
        if before["digest"] != source["digest"] or after["digest"] != source["digest"]:
            parsed["status"] = "source_changed"
        check = {"id": spec["id"], "argv": spec["argv"], "kind": spec["kind"],
                 "spec_digest": state.digest(spec), "environment_fingerprint": fingerprint,
                 "exit_code": code, "duration_seconds": time.time() - begin, "reused": False, **parsed}
        for key, text in (("stdout", stdout), ("stderr", stderr)):
            path = log_dir / (spec["id"] + "." + key)
            path.write_text(text)
            path.chmod(0o600)
            check[key + "_path"], check[key + "_sha256"] = str(path), state.file_hash(path)
        result["checks"].append(check)
        if code == 130:
            result["cancelled"] = True
            break
    result["not_run"] = [c["id"] for c in plan["check_manifest"]["checks"] if c["id"] not in {x["id"] for x in result["checks"]}]
    result["end"] = time.time()
    run_id = state.digest(result)
    state.save(state.storage(root) / "runs" / (run_id + ".json"), result)
    return run_id, result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=["init", "run", "show"])
    p.add_argument("issue", help="Issue URL, or a run ID for show")
    p.add_argument("--plan")
    p.add_argument("--reuse", action="store_true", help="Explicitly reuse matching source/spec/declared-environment checks; not for changed external state")
    args = p.parse_args()
    root = state.repo()
    if args.action == "show":
        print(json.dumps(load_run(root, args.issue), indent=2))
        return
    if not args.plan:
        p.error("--plan is required")
    import handoff
    issue, comments = handoff.issue_and_comments(args.issue)
    plan, contract = approved_plan(issue, comments, args.plan)
    if args.action == "init":
        print(json.dumps({"manifest": str(initialize(root, plan)), "outcome": "initialized_or_matching"}))
        return
    run_id, result = run_checks(root, issue, args.plan, plan, contract, args.reuse)
    summary = {"run_id": run_id, "source": result["source"], "contract_revision": contract["revision"],
               "checks": [{k: c[k] for k in ("id", "status", "exit_code", "test_count", "skips", "duration_seconds", "reused")} for c in result["checks"]],
               "not_run": result["not_run"], "detail_command": "verify.py show " + run_id}
    print(json.dumps(summary, indent=2))
    required = {c["id"] for c in plan["check_manifest"]["checks"] if c.get("required", True)}
    if set(result["not_run"]) & required or any(c["id"] in required and c["status"] != "pass" for c in result["checks"]):
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
