#!/usr/bin/env python3
"""Create local workflow settings without modifying OpenCode or GitHub."""
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tracking"))
from private_config import config_path, load, validate_tracking


def parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skills-path", action="append", default=[])
    parser.add_argument("--project-owner")
    parser.add_argument("--project-number", type=int)
    models = parser.add_mutually_exclusive_group()
    models.add_argument("--profiles-file")
    models.add_argument("--model")
    parser.add_argument("--variant", default="")
    return parser


def configure(args):
    data = {"version": 1}
    destination = config_path()
    if destination.exists() or destination.is_symlink():
        raise RuntimeError("Preserving existing settings: " + str(destination))
    if args.variant and not args.model:
        raise RuntimeError("--variant requires --model")
    if args.model and ("/" not in args.model or any(not part for part in args.model.split("/", 1))):
        raise RuntimeError("--model requires PROVIDER/MODEL")
    if args.project_owner is not None or args.project_number is not None:
        data["tracking"] = {"owner": args.project_owner, "number": args.project_number}
        validate_tracking(data["tracking"])
    if args.skills_path:
        data["skills_paths"] = [str(Path(p).expanduser().resolve()) for p in args.skills_path]
        if any(not Path(p).is_dir() for p in data["skills_paths"]):
            raise RuntimeError("Configured private skills directory does not exist")
    if args.profiles_file:
        path = Path(args.profiles_file).expanduser().resolve()
        if not path.is_file():
            raise RuntimeError("Configured profiles file does not exist")
        data["profiles_file"] = str(path)
    generated = destination.parent / "profiles.json" if args.model else None
    if generated and (generated == destination or generated.exists() or generated.is_symlink()):
        raise RuntimeError("Preserving existing profile: " + str(generated))
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation preserves existing settings, including on repeated setup.
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    created_profile = False
    try:
        with os.fdopen(fd, "w") as output:
            if generated:
                profile_fd = os.open(generated, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                created_profile = True
                with os.fdopen(profile_fd, "w") as profile:
                    json.dump({"version": 1, "default": "custom",
                               "defaults": {"model": args.model, "variant": args.variant},
                               "profiles": {"custom": {}}}, profile, indent=2)
                    profile.write("\n")
                data["profiles_file"] = generated.name
            output.write(json.dumps(data, indent=2) + "\n")
        load()
    except Exception:
        destination.unlink()
        if created_profile:
            generated.unlink()
        raise
    print("Created " + str(destination))
    print("Run workflow.py doctor --github, then restart OpenCode through the launcher.")


def main(argv=None):
    configure(parser().parse_args(argv))


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
