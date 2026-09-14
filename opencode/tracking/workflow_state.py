#!/usr/bin/env python3
"""Local, content-addressed workflow evidence. No Git index or worktree mutations."""
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile


def digest(value):
    raw = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def git(*args, cwd=None):
    return subprocess.check_output(["git", *args], cwd=cwd, stderr=subprocess.PIPE,
        env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})


def root(cwd=None):
    return Path(git("rev-parse", "--show-toplevel", cwd=cwd).decode().strip()).resolve()


def directory(cwd=None):
    base = Path(os.environ.get("OPENCODE_WORKFLOW_STATE", str(Path.home() / ".local/state/opencode-workflow")))
    result = base / "repositories" / digest(str(root(cwd)))
    repo = root(cwd)
    if result.resolve() == repo or repo in result.resolve().parents:
        raise RuntimeError("Workflow state must live outside the source worktree")
    result.mkdir(parents=True, exist_ok=True, mode=0o700)
    return result


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    data = value if isinstance(value, bytes) else (json.dumps(value, indent=2) + "\n").encode()
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
        temporary = Path(f.name)
        f.write(data)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def load_object(kind, key, cwd=None):
    if not isinstance(key, str) or len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
        raise RuntimeError("Invalid local evidence identifier")
    path = directory(cwd) / kind / (key + ".json")
    try:
        value = json.loads(path.read_text())
    except FileNotFoundError as error:
        raise RuntimeError("Local evidence unavailable; regenerate it: " + key) from error
    if digest(value) != key:
        raise RuntimeError("Local evidence was modified: " + key)
    return value


def store_object(kind, value, cwd=None):
    key = digest(value)
    write(directory(cwd) / kind / (key + ".json"), value)
    return key


def snapshot(cwd=None):
    repo = root(cwd)
    if git("ls-files", "--unmerged", cwd=repo):
        raise RuntimeError("Resolve merge conflicts before recording evidence")
    names = lambda raw: {os.fsdecode(p) for p in raw.split(b"\0") if p}
    tracked = names(git("ls-files", "-z", cwd=repo))
    untracked = names(git("ls-files", "--others", "--exclude-standard", "-z", cwd=repo))
    staged = names(git("diff", "--cached", "--name-only", "-z", cwd=repo))
    unstaged = names(git("diff", "--name-only", "-z", cwd=repo))
    changed = names(git("diff", "HEAD", "--name-only", "-z", cwd=repo)) | untracked | staged
    partial = sorted(staged & (unstaged | untracked))
    index = digest(git("diff", "--cached", "--binary", "--", *partial, cwd=repo)) if partial else None
    entries = {}
    for name in sorted(tracked | untracked):
        path = repo / name
        try:
            mode = path.lstat().st_mode
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(mode):
            raw = os.fsencode(os.readlink(path))
        elif stat.S_ISREG(mode):
            raw = path.read_bytes()
        else:
            raise RuntimeError("Explicit evidence needed for submodule/special file: " + name)
        sha = digest(raw)
        entries[name] = {"sha256": sha, "mode": stat.S_IFMT(mode) | (mode & 0o111)}
        if name in changed and len(raw) <= 1024 * 1024 and b"\0" not in raw:
            write(directory(repo) / "blobs" / sha, raw)
    content = digest(entries)
    head = git("rev-parse", "HEAD", cwd=repo).decode().strip()
    local = {"head": head, "files": entries, "changed_files": sorted(changed)}
    key = store_object("snapshots", local, repo)
    return {"version": 2, "head": head, "branch": git("branch", "--show-current", cwd=repo).decode().strip(),
            "content_digest": content, "digest": digest({"content": content, "partial_index": index}),
            "snapshot_id": key, "changed_files": sorted(changed), "partially_staged_files": partial}


def delta(before, after, cwd=None):
    import difflib
    repo = root(cwd)
    try:
        old = load_object("snapshots", before["snapshot_id"], repo)
        new = load_object("snapshots", after["snapshot_id"], repo)
    except (RuntimeError, KeyError):
        return {"available": False, "reason": "Prior local snapshot unavailable; inspect the full intended diff"}
    changed = sorted(name for name in set(old["files"]) | set(new["files"])
                     if old["files"].get(name) != new["files"].get(name))
    def contents(record, name):
        entry = record["files"].get(name)
        if entry is None:
            return b""
        blob = directory(repo) / "blobs" / entry["sha256"]
        if blob.exists():
            raw = blob.read_bytes()
        elif name not in record["changed_files"]:
            try:
                raw = git("show", record["head"] + ":" + name, cwd=repo)
            except subprocess.CalledProcessError:
                return None
        else:
            return None
        return raw if digest(raw) == entry["sha256"] else None
    patches, unavailable = [], []
    for name in changed:
        a, b = contents(old, name), contents(new, name)
        if a is None or b is None or b"\0" in a or b"\0" in b:
            unavailable.append(name)
            continue
        patches.extend(difflib.unified_diff(a.decode(errors="replace").splitlines(True),
            b.decode(errors="replace").splitlines(True), fromfile="reviewed/" + name, tofile="current/" + name))
    patch = "".join(patches).encode()
    location = directory(repo) / "deltas" / (digest(patch) + ".diff")
    write(location, patch)
    return {"available": True, "changed_files": changed, "patch_file": str(location),
            "patch_sha256": digest(patch), "requires_direct_inspection": unavailable,
            "note": "Mode/symlink changes are included in changed_files; inspect their metadata as well as text"}


def file_hash(path):
    h = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def confined(repo, value):
    if not isinstance(value, str) or Path(value).is_absolute() or ".." in Path(value).parts:
        raise RuntimeError("Expected a repository-relative path: " + str(value))
    path = repo / value
    if repo.resolve() not in path.resolve().parents:
        raise RuntimeError("Expected a repository-relative path: " + str(value))
    return path


# Shared names for the runner and GitHub handoff layer.
repo = root
storage = directory
save = write
