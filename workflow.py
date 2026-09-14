#!/usr/bin/env python3
"""Install, uninstall or launch self-contained OpenCode workflow resources (stdlib only)."""
import argparse
import os
from pathlib import Path
import shlex
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "opencode/runtime"))
import launch
import setup


def launcher_content():
    return ("#!/bin/sh\n# Generated OpenCode workflow consumer; no global config changes.\nexec "
            + shlex.quote(sys.executable) + " " + shlex.quote(str(ROOT / "workflow.py")) + ' "$@"\n')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["install", "uninstall", "setup", "launch", "prepare", "doctor"])
    parser.add_argument("args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.operation == "setup":
        setup.main(args.args)
    elif args.operation == "install":
        install = setup.parser()
        install.add_argument("--bin-dir", default=str(Path.home() / ".local/bin"))
        install.add_argument("--launcher-only", action="store_true")
        options = install.parse_args(args.args)
        if options.launcher_only and any((options.model, options.profiles_file, options.variant,
                                         options.skills_path, options.project_owner, options.project_number)):
            install.error("--launcher-only cannot be combined with setup options")
        target = Path(options.bin_dir).expanduser().resolve() / "opencode-workflow"
        if target.exists() or target.is_symlink():
            raise RuntimeError("Preserving existing launcher: " + str(target))
        if not options.launcher_only:
            setup.configure(options)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o755)
        with os.fdopen(fd, "w") as output:
            output.write(launcher_content())
        print("Installed " + str(target))
        print("Add its directory to PATH; from your application repo run: opencode-workflow launch")
    elif args.operation == "uninstall":
        uninstall = argparse.ArgumentParser(description="Remove this checkout's generated launcher; keep settings and state.")
        uninstall.add_argument("--bin-dir", default=str(Path.home() / ".local/bin"))
        options = uninstall.parse_args(args.args)
        target = Path(options.bin_dir).expanduser().resolve() / "opencode-workflow"
        if target.is_symlink():
            raise RuntimeError("Preserving unrecognized launcher: " + str(target))
        if not target.exists():
            print("Launcher already absent: " + str(target))
            return
        if not target.is_file() or target.read_bytes() != launcher_content().encode():
            raise RuntimeError("Preserving unrecognized launcher: " + str(target)
                               + "; expected the unmodified wrapper for this checkout and Python interpreter")
        target.unlink()
        print("Removed " + str(target))
        print("Workflow settings, private skills and state were preserved.")
    else:
        prefix = {"prepare": ["--prepare"], "doctor": ["--doctor"], "launch": []}[args.operation]
        launch.main(prefix + args.args)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError, KeyError) as error:
        print("workflow: " + str(error), file=sys.stderr)
        sys.exit(1)
