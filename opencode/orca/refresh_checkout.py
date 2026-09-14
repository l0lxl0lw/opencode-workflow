#!/usr/bin/env python3
"""Refresh one explicitly named checkout; discard only tracked unstaged edits."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys


def git(path, *args, check=True):
    result = subprocess.run(
        ["git", "-C", str(path), *args], text=True, capture_output=True,
        timeout=120, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    if check and result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "Git command failed")
    return result


def validate(path, expected_origin, branch):
    path = Path(path).resolve(strict=True)
    root = Path(git(path, "rev-parse", "--show-toplevel").stdout.strip()).resolve()
    if root != path:
        raise RuntimeError("Target must be the exact checkout root")
    if git(path, "remote", "get-url", "origin").stdout.strip() != expected_origin:
        raise RuntimeError("origin differs from the explicitly configured remote")
    if git(path, "symbolic-ref", "--short", "HEAD").stdout.strip() != branch:
        raise RuntimeError("Checkout is not on the configured branch: " + branch)
    gitdir = Path(git(path, "rev-parse", "--absolute-git-dir").stdout.strip())
    for marker in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply", "sequencer", "BISECT_LOG", "index.lock"):
        if (gitdir / marker).exists():
            raise RuntimeError("Unfinished Git operation: " + marker)
    if git(path, "diff", "--cached", "--quiet", check=False).returncode != 0:
        raise RuntimeError("Staged changes must be handled before scheduled refresh")
    # A superproject refresh cannot establish cleanliness inside submodules.
    if (path / ".gitmodules").exists():
        raise RuntimeError("Submodule checkouts require a repository-specific refresh policy")
    return path, gitdir


def refresh(path, expected_origin, branch="main", apply=False):
    path, gitdir = validate(path, expected_origin, branch)
    if not apply:
        return {"outcome": "precheck_passed", "path": str(path), "branch": branch}
    # Serialize duplicate scheduled invocations of this helper in the same checkout.
    with (gitdir / "opencode-refresh.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Another scheduled refresh is already running")
        validate(path, expected_origin, branch)
        before = git(path, "rev-parse", "HEAD").stdout.strip()
        ref = "refs/remotes/origin/" + branch
        git(path, "fetch", "--no-tags", "origin", "+refs/heads/" + branch + ":" + ref)
        target = git(path, "rev-parse", ref).stdout.strip()
        if git(path, "merge-base", "--is-ancestor", before, target, check=False).returncode != 0:
            raise RuntimeError("Local-only commits or divergent history; nothing discarded")
        # Recheck immediately before the explicitly authorized discard.
        validate(path, expected_origin, branch)
        if git(path, "rev-parse", "HEAD").stdout.strip() != before:
            raise RuntimeError("HEAD changed during refresh; retry after other work finishes")
        discarded = git(path, "diff", "--name-only", "-z").stdout.rstrip("\0").split("\0")
        git(path, "restore", "--source=HEAD", "--worktree", "--", ".")
        try:
            # Unlike reset --hard / clean, merge refuses untracked-file collisions.
            git(path, "merge", "--ff-only", "--no-edit", "--no-overwrite-ignore", target)
        except RuntimeError as error:
            raise RuntimeError("Tracked unstaged edits were discarded, but fast-forward failed: " + str(error)) from error
        after = git(path, "rev-parse", "HEAD").stdout.strip()
        if after != target:
            raise RuntimeError("Refresh verification failed: HEAD does not match fetched target")
        return {"outcome": "refreshed", "path": str(path), "branch": branch,
                "before": before, "head": after, "discardedTrackedPaths": [p for p in discarded if p]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", required=True)
    parser.add_argument("--origin", required=True, help="Exact expected origin URL")
    parser.add_argument("--branch", default="main")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Read-only local precheck; no fetch or discard")
    mode.add_argument("--apply", action="store_true", help="Fetch, discard tracked unstaged edits, fast-forward")
    args = parser.parse_args()
    try:
        print(json.dumps(refresh(args.path, args.origin, args.branch, args.apply), indent=2))
        return 0
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"outcome": "failed", "error": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
