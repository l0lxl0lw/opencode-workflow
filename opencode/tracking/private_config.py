"""Optional machine configuration. Never copied into public resource bundles."""
import json
import os
from pathlib import Path


def config_path(environ=None):
    env = os.environ if environ is None else environ
    home = Path(env.get("HOME", str(Path.home())))
    base = Path(env.get("XDG_CONFIG_HOME") or home / ".config")
    raw = env.get("OPENCODE_PRIVATE_CONFIG", str(base / "opencode-workflow/config.json"))
    return home / raw[2:] if raw.startswith("~/") else Path(raw)


def load(environ=None):
    env = os.environ if environ is None else environ
    home = Path(env.get("HOME", str(Path.home())))
    path = config_path(env)
    if not path.exists():
        if "OPENCODE_PRIVATE_CONFIG" in env:
            raise RuntimeError("Explicit private workflow configuration does not exist")
        return {}
    try:
        data = json.loads(path.read_text())
    except (ValueError, OSError) as error:
        raise RuntimeError("Cannot read private workflow configuration") from error
    if not isinstance(data, dict) or data.get("version") != 1:
        raise RuntimeError("Private workflow configuration requires version 1")
    allowed = {"version", "skills_paths", "tracking", "profiles_file"}
    if set(data) - allowed:
        raise RuntimeError("Unknown private workflow configuration field")
    paths = data.get("skills_paths", [])
    if not isinstance(paths, list) or any(not isinstance(p, str) for p in paths):
        raise RuntimeError("skills_paths must contain paths")
    resolved = []
    for raw in paths:
        p = home / raw[2:] if raw.startswith("~/") else Path(raw)
        p = p if p.is_absolute() else path.parent / p
        if not p.is_dir():
            raise RuntimeError("Configured private skills directory does not exist")
        resolved.append(str(p.resolve()))
    result = {**data, "skills_paths": resolved}
    if "profiles_file" in data:
        raw = data["profiles_file"]
        if not isinstance(raw, str) or not raw:
            raise RuntimeError("profiles_file must be a path")
        p = home / raw[2:] if raw.startswith("~/") else Path(raw)
        p = p if p.is_absolute() else path.parent / p
        if not p.is_file():
            raise RuntimeError("Configured profiles file does not exist")
        result["profiles_file"] = str(p.resolve())
    if "tracking" in data:
        validate_tracking(data["tracking"])
    return result


def validate_tracking(value):
    if (not isinstance(value, dict) or set(value) != {"owner", "number"}
            or not isinstance(value.get("owner"), str) or not value["owner"].strip()
            or type(value.get("number")) is not int or value["number"] < 1):
        raise RuntimeError("Configure tracking.owner and tracking.number in private workflow configuration")
    return value["owner"], value["number"]


def tracking_project():
    value = load().get("tracking", {})
    return validate_tracking(value)


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Inspect non-secret workflow registration status")
    parser.add_argument("--tracking-status", action="store_true", required=True)
    parser.parse_args()
    try:
        print("configured" if "tracking" in load() else "not_configured")
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
