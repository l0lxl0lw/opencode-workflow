#!/usr/bin/env python3
"""Issue/project tracking and read-only branch freshness monitoring. Python stdlib only."""
import argparse
import contextlib
import datetime
import fcntl
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import operational
from private_config import tracking_project, load as load_private_config

STATUSES = ["Backlog", "Researching", "Planning", "Ready", "Implementing", "In review", "Done"]
SYNC = ["Not started", "Unchecked", "Up to date", "Needs sync", "Syncing", "Conflicts", "Verifying"]
STATE = Path(os.environ.get("OPENCODE_TRACK_STATE", str(Path.home() / ".local/state/opencode-track")))
ISSUE_PATTERN = re.compile(r"https://github\.com/([^/]+/[^/]+)/issues/(\d+)")
ORCA_STAGES = {
    "Backlog": ("todo", "ticket created; awaiting research"),
    "Researching": ("in-progress", "research in progress"),
    "Planning": ("in-progress", "planning in progress"),
    "Ready": ("todo", "plan ready; awaiting execution approval"),
    "Implementing": ("in-progress", "implementing; verification next"),
    "In review": ("in-review", "ready for independent review"),
    "Done": ("completed", "accepted and required PRs merged"),
}


class OrcaError(RuntimeError):
    def __init__(self, reason, message, data=None, worktree=None):
        super().__init__(message)
        self.reason = reason
        self.data = data
        self.worktree = worktree


def run(*args, cwd=None):
    p = subprocess.run(args, cwd=cwd, text=True, capture_output=True, timeout=90)
    if p.returncode:
        raise RuntimeError(p.stderr.strip() or p.stdout.strip() or "Command failed: " + str(args))
    return p.stdout.strip()


def gh(*args):
    return json.loads(run("gh", *args))


def orca(*args):
    try:
        process = subprocess.run(
            ("orca", *args), text=True, capture_output=True, timeout=90
        )
    except FileNotFoundError as error:
        raise OrcaError("orca_unavailable", "the orca CLI is not on PATH") from error
    except subprocess.TimeoutExpired as error:
        raise OrcaError("orca_timeout", "Orca command timed out") from error
    except OSError as error:
        raise OrcaError("orca_process_error", str(error)) from error
    try:
        response = json.loads(process.stdout)
    except (json.JSONDecodeError, TypeError) as error:
        detail = process.stderr.strip() or process.stdout.strip() or "empty response"
        raise OrcaError("malformed_orca_response", detail) from error
    if not isinstance(response, dict) or type(response.get("ok")) is not bool:
        raise OrcaError("malformed_orca_response", "Orca returned an invalid JSON envelope")
    if not response["ok"]:
        failure = response.get("error")
        if not isinstance(failure, dict):
            raise OrcaError("malformed_orca_response", "Orca returned an invalid error envelope")
        reason = failure.get("code")
        message = failure.get("message")
        if not isinstance(reason, str) or not isinstance(message, str):
            raise OrcaError("malformed_orca_response", "Orca returned an invalid error envelope")
        raise OrcaError(reason, message, failure.get("data"))
    if process.returncode:
        raise OrcaError("orca_process_error", process.stderr.strip() or "Orca exited unsuccessfully")
    return response


def graphql(query, **variables):
    args = ["api", "graphql", "-f", "query=" + query]
    for key, value in variables.items():
        args.extend(["-f", key + "=" + value])
    result = gh(*args)
    if result.get("errors"):
        raise RuntimeError(json.dumps(result["errors"]))
    return result["data"]


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


@contextlib.contextmanager
def registry():
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (STATE / "lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = STATE / "branches.json"
        data = json.loads(path.read_text()) if path.exists() else {}
        try:
            yield data
        finally:
            fd, temp = tempfile.mkstemp(dir=STATE)
            with os.fdopen(fd, "w") as out:
                json.dump(data, out, indent=2)
            os.replace(temp, path)


def project():
    OWNER, NUMBER = tracking_project()
    p = gh("project", "view", str(NUMBER), "--owner", OWNER, "--format", "json")
    fields = gh("project", "field-list", str(NUMBER), "--owner", OWNER, "--limit", "100", "--format", "json")
    return p["id"], {f["name"]: f for f in fields["fields"]}


def configure():
    OWNER, NUMBER = tracking_project()
    pid, fields = project()
    for name, choices in [("Status", STATUSES), ("Branch sync", SYNC)]:
        if name in fields:
            existing = [o["name"] for o in fields[name].get("options", [])]
            if existing == choices:
                continue
            # Replacing options invalidates option IDs; refuse populated projects.
            items = gh("project", "item-list", str(NUMBER), "--owner", OWNER, "--limit", "1", "--format", "json")
            if items["totalCount"]:
                raise RuntimeError("Project contains items; migrate field options explicitly before configuring")
            options = [{"name": c, "color": "GRAY", "description": c} for c in choices]
            query = "mutation { updateProjectV2Field(input:{fieldId:" + json.dumps(fields[name]["id"]) + ",singleSelectOptions:" + "[" + ",".join("{name:" + json.dumps(o["name"]) + ",color:GRAY,description:" + json.dumps(o["description"]) + "}" for o in options) + "]}) { projectV2Field { ... on ProjectV2SingleSelectField { id } } } }"
            graphql(query)
        else:
            run("gh", "project", "field-create", str(NUMBER), "--owner", OWNER, "--name", name,
                "--data-type", "SINGLE_SELECT", "--single-select-options", ",".join(choices))
    print(f"Configured project {OWNER}/{NUMBER}")


def issue_details(value):
    if not isinstance(value, str):
        raise RuntimeError("Use a GitHub issue URL (or a number in its repository)")
    if value.isdigit():
        try:
            repo_result = gh("repo", "view", "--json", "nameWithOwner")
        except json.JSONDecodeError as error:
            raise RuntimeError("GitHub returned invalid JSON") from error
        repo = repo_result.get("nameWithOwner") if isinstance(repo_result, dict) else None
        if not isinstance(repo, str) or not re.fullmatch(r"[^/]+/[^/]+", repo):
            raise RuntimeError("GitHub returned an invalid repository identity")
        value = "https://github.com/" + repo + "/issues/" + value
    if not ISSUE_PATTERN.fullmatch(value):
        raise RuntimeError("Use a GitHub issue URL (or a number in its repository)")
    # GitHub's canonical response, rather than caller text, supplies link identity.
    try:
        issue = gh("issue", "view", value, "--json", "number,url")
    except json.JSONDecodeError as error:
        raise RuntimeError("GitHub returned invalid JSON") from error
    number = issue.get("number") if isinstance(issue, dict) else None
    url = issue.get("url") if isinstance(issue, dict) else None
    match = ISSUE_PATTERN.fullmatch(url) if isinstance(url, str) else None
    if not match:
        raise RuntimeError("GitHub returned an invalid issue URL")
    if type(number) is not int or number <= 0 or int(match.group(2)) != number:
        raise RuntimeError("GitHub returned an invalid issue number")
    return {"url": url, "number": number, "repository": match.group(1)}


def issue_url(value):
    return issue_details(value)["url"]


def validated_worktree(response, repository):
    result = response.get("result")
    worktree = result.get("worktree") if isinstance(result, dict) else None
    if not isinstance(worktree, dict):
        raise OrcaError("malformed_orca_response", "Orca response has no worktree")
    worktree_id = worktree.get("id")
    project_id = worktree.get("projectId")
    path = worktree.get("path")
    linked = worktree.get("linkedIssue")
    if not isinstance(worktree_id, str) or not worktree_id:
        raise OrcaError("malformed_orca_response", "Orca worktree has no id")
    if not isinstance(path, str) or not path or not Path(path).is_absolute():
        raise OrcaError("malformed_orca_response", "Orca worktree has no absolute path")
    if not isinstance(project_id, str) or not project_id.lower().startswith("github:"):
        raise OrcaError(
            "malformed_orca_response", "Orca worktree has no GitHub project identity",
            worktree=worktree
        )
    if project_id[7:].lower() != repository.lower():
        raise OrcaError(
            "repository_mismatch", "Issue and Orca worktree repositories differ",
            worktree=worktree
        )
    if linked is not None and (type(linked) is not int or linked <= 0):
        raise OrcaError(
            "malformed_linked_issue", "Orca worktree has an invalid linkedIssue",
            worktree=worktree
        )
    return worktree


def link_orca(value, replace_existing=None):
    if replace_existing is not None and (type(replace_existing) is not int or replace_existing <= 0):
        return {
            "outcome": "failed", "reason": "invalid_replacement",
            "issue": {"input": value}, "observed": replace_existing
        }, 1
    try:
        issue = issue_details(value)
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as error:
        return {
            "outcome": "failed", "reason": "invalid_issue",
            "issue": {"input": value}, "observed": str(error)
        }, 1
    base_recovery = "python3 " + shlex.quote(str(Path(__file__).resolve())) + " link-orca " + issue["url"]
    recovery = base_recovery
    if replace_existing is not None:
        recovery += " --replace-existing " + str(replace_existing)

    def outcome(name, reason=None, worktree=None, existing=None, observed=None):
        result = {"outcome": name, "reason": reason, "issue": issue}
        if worktree:
            result["worktree"] = {
                key: worktree[key] for key in ("id", "projectId", "path") if key in worktree
            }
        if existing is not None:
            result["existingIssue"] = existing
        if observed is not None:
            result["observed"] = observed
        if name in ("orca_unavailable", "conflict", "failed"):
            result["recoveryCommand"] = recovery
        return result

    def failed(error, stage, worktree=None):
        reason = error.reason
        if reason == "invalid_argument" and "local cwd shortcut" in str(error) and "remote runtime" in str(error):
            reason = "remote_runtime_unsupported"
        elif reason not in (
            "runtime_unavailable", "malformed_orca_response", "repository_mismatch",
            "malformed_linked_issue", "remote_runtime_unsupported"
        ):
            reason = stage + "_error"
        result = outcome("failed", reason, worktree or error.worktree, observed=str(error))
        if error.data is not None:
            result["details"] = error.data
        return result, 1

    try:
        current = validated_worktree(
            orca("worktree", "current", "--json"), issue["repository"]
        )
    except OrcaError as error:
        if error.reason == "selector_not_found":
            return outcome("not_managed", error.reason), 0
        if error.reason == "orca_unavailable":
            return outcome("orca_unavailable", error.reason, observed=str(error)), 0
        return failed(error, "current")

    linked = current.get("linkedIssue")
    if linked == issue["number"]:
        return outcome("already_attached", worktree=current), 0
    if linked is not None:
        if replace_existing != linked:
            reason = "linked_issue_conflict" if replace_existing is None else "stale_replacement"
            result = outcome("conflict", reason, current, linked, replace_existing)
            result["recoveryCommand"] = base_recovery + " --replace-existing " + str(linked)
            return result, 2
    elif replace_existing is not None:
        result = outcome("conflict", "stale_replacement", current, replace_existing)
        result["recoveryCommand"] = base_recovery
        return result, 2

    try:
        updated = validated_worktree(
            orca(
                "worktree", "set", "--worktree", "id:" + current["id"],
                "--issue", str(issue["number"]), "--json"
            ),
            issue["repository"],
        )
    except OrcaError as error:
        return failed(error, "setter", current)
    if (updated["id"] != current["id"] or updated["path"] != current["path"] or
            updated.get("linkedIssue") != issue["number"]):
        return outcome("failed", "invalid_setter_confirmation", current, observed={
            "id": updated["id"], "path": updated["path"],
            "linkedIssue": updated.get("linkedIssue")
        }), 1

    try:
        verified = validated_worktree(
            orca("worktree", "current", "--json"), issue["repository"]
        )
    except OrcaError as error:
        return failed(error, "verification", current)
    if (verified["id"] != current["id"] or verified["path"] != current["path"] or
            verified.get("linkedIssue") != issue["number"]):
        return outcome("failed", "verification_mismatch", current, observed={
            "id": verified["id"], "path": verified["path"],
            "linkedIssue": verified.get("linkedIssue")
        }), 1
    return outcome("attached", worktree=verified), 0


def checkpoint_orca(value, stage, summary=None):
    """Mirror a milestone only to the enclosing, already-linked workspace."""
    current = None
    recovery = "python3 " + shlex.quote(str(Path(__file__).resolve())) + " checkpoint-orca " + shlex.quote(value) + " " + shlex.quote(stage)
    if summary is not None:
        recovery += " --summary " + shlex.quote(summary)
    try:
        if stage not in ORCA_STAGES or (summary is not None and (not summary.strip() or "\n" in summary or "\r" in summary)):
            raise RuntimeError("Use a known stage and a nonempty single-line summary")
        issue = issue_details(value)
        current = validated_worktree(orca("worktree", "current", "--json"), issue["repository"])
        if current.get("linkedIssue") != issue["number"]:
            return {
                "outcome": "not_linked" if current.get("linkedIssue") is None else "conflict",
                "existingIssue": current.get("linkedIssue"),
                "recoveryCommand": "python3 " + shlex.quote(str(Path(__file__).resolve())) + " link-orca " + issue["url"],
            }, 2
        status, default_summary = ORCA_STAGES[stage]
        old_comment = current.get("comment", "")
        if not isinstance(old_comment, str):
            raise RuntimeError("Orca returned a non-text workspace comment")
        # Replace only this issue's owned line; preserve user goals and other notes.
        prefix = "[opencode-workflow #" + str(issue["number"]) + "] "
        line = prefix + stage + ": " + (summary.strip() if summary is not None else default_summary)
        lines = old_comment.split("\n") if old_comment else []
        kept = [part for part in lines if not part.startswith(prefix)]
        comment = "\n".join([line, *kept])
        base = {"issue": issue["url"], "worktreeId": current["id"], "workspaceStatus": status, "comment": comment}
        if old_comment == comment and current.get("workspaceStatus") == status:
            return {"outcome": "already_updated", **base}, 0
        selector = "id:" + current["id"]
        response = orca("worktree", "set", "--worktree", selector,
                        "--comment", comment, "--workspace-status", status, "--json")
        # Both the mutation receipt and a fresh read must confirm the exact target.
        for observed in (response, orca("worktree", "show", "--worktree", selector, "--json")):
            actual = validated_worktree(observed, issue["repository"])
            if any(actual.get(key) != expected for key, expected in {
                "id": current["id"], "path": current["path"], "linkedIssue": issue["number"],
                "comment": comment, "workspaceStatus": status,
            }.items()):
                raise OrcaError("verification_mismatch", "Orca milestone did not persist on the expected linked workspace")
        return {"outcome": "updated", **base}, 0
    except OrcaError as error:
        if error.reason == "selector_not_found":
            # Only the initial current lookup can establish an unmanaged cwd.
            if current is None:
                return {"outcome": "not_managed"}, 0
        result = {"outcome": "failed", "reason": error.reason, "observed": str(error), "recoveryCommand": recovery}
        if error.data is not None:
            result["details"] = error.data
        return result, 1
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as error:
        return {"outcome": "failed", "observed": str(error), "recoveryCommand": recovery}, 1


def workflow_status(value, stage):
    """Report GitHub and Orca independently; neither failure hides the other."""
    try:
        updated = set_field(value, "Status", stage)
        github = {"outcome": "not_configured"} if updated is False else {"outcome": "updated", "status": stage}
        github_exit = 0
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as error:
        github = {"outcome": "failed", "observed": str(error)}
        github_exit = 1
    checkpoint, orca_exit = checkpoint_orca(value, stage)
    if checkpoint.get("reason") == "orca_unavailable":
        # The combined stage command remains usable without optional supervision.
        # Explicit link-orca/checkpoint-orca requests still report CLI failures.
        checkpoint, orca_exit = {"outcome": "not_configured", "reason": "orca_unavailable"}, 0
    return {"github": github, "orca": checkpoint}, github_exit or orca_exit


def item(value):
    owner, number = tracking_project()
    return gh("project", "item-add", str(number), "--owner", owner, "--url", value, "--format", "json")["id"]


def set_field(value, name, selection):
    # Issue-only mode still registers branches and publishes issue artifacts.
    # Invalid/explicitly missing configuration raises; it is never a silent skip.
    if "tracking" not in load_private_config():
        return False
    pid, fields = project()
    if name not in fields:
        raise RuntimeError("Missing project field: " + name)
    option = next((o["id"] for o in fields[name]["options"] if o["name"] == selection), None)
    if not option:
        raise RuntimeError("Missing option: " + selection)
    iid = item(value)
    run("gh", "project", "item-edit", "--id", iid, "--project-id", pid,
        "--field-id", fields[name]["id"], "--single-select-option-id", option)
    result = graphql('query($id:ID!,$name:String!){node(id:$id){... on ProjectV2Item{fieldValueByName(name:$name){... on ProjectV2ItemFieldSingleSelectValue{name}}}}}', id=iid, name=name)
    actual = result["node"]["fieldValueByName"]
    if not actual or actual.get("name") != selection:
        raise RuntimeError("Project field update did not persist: " + name)
    return True


def note(value, heading, body, key=None):
    marker = "<!-- opencode-track:" + key + " -->" if key else ""
    if marker:
        repo, number = value.split("github.com/")[1].split("/issues/")
        pages = gh("api", "--paginate", "--slurp", "repos/" + repo + "/issues/" + number + "/comments")
        if any(marker in c["body"] for page in pages for c in page):
            return
    text = ("## " + heading + "\n\n" + body + "\n\n" + marker).strip()
    print(run("gh", "issue", "comment", value, "--body", operational.wrap(text)))


def git(cwd, *args):
    return run("git", *args, cwd=cwd)


def register(value):
    cwd = git(None, "rev-parse", "--show-toplevel")
    repo = gh("repo", "view", "--json", "nameWithOwner,defaultBranchRef")
    expected = value.split("github.com/")[1].split("/issues/")[0]
    if repo["nameWithOwner"].lower() != expected.lower():
        raise RuntimeError("Issue and worktree repository differ")
    branch = git(cwd, "symbolic-ref", "--short", "HEAD")
    target = repo["defaultBranchRef"]["name"]
    if branch == target:
        raise RuntimeError("Register an implementation branch, not the default branch")
    common = str(Path(git(cwd, "rev-parse", "--git-common-dir")).resolve())
    if not Path(git(cwd, "rev-parse", "--git-common-dir")).is_absolute():
        common = str((Path(cwd) / git(cwd, "rev-parse", "--git-common-dir")).resolve())
    origin = git(cwd, "remote", "get-url", "origin")
    remote_repo = re.sub(r"\.git$", "", origin.rstrip("/"))
    if remote_repo.lower() not in ("https://github.com/" + expected.lower(), "git@github.com:" + expected.lower(), "ssh://git@github.com/" + expected.lower()):
        raise RuntimeError("origin must refer to the issue repository")
    with registry() as data:
        if value in data:
            old = data[value]
            if old["common"] != common or old["branch"] != branch:
                raise RuntimeError("Issue already tracks another branch; unregister it explicitly first")
            old["path"] = cwd
        else:
            if any(r["common"] == common and r["branch"] == branch for r in data.values()):
                raise RuntimeError("Branch already registered to another issue")
            set_field(value, "Branch sync", "Unchecked")
            data[value] = dict(path=cwd, common=common, branch=branch, target=target, state="Unchecked", observed=None)
        note(value, "Branch tracking", "Branch: `" + branch + "`\n\nTarget: `origin/" + target + "`\n\nAutomatic detection; sync requires an explicit request.", "register-" + branch)


def locate(record):
    # Git's common directory survives linked-worktree renames; recover the path.
    text = run("git", "--git-dir=" + record["common"], "worktree", "list", "--porcelain")
    for block in text.split("\n\n"):
        entries = dict(line.split(" ", 1) for line in block.splitlines() if " " in line)
        if entries.get("branch") == "refs/heads/" + record["branch"]:
            path = entries["worktree"]
            if git(path, "symbolic-ref", "--short", "HEAD") == record["branch"]:
                record["path"] = path
                return path
        # A rebase temporarily detaches HEAD. Identify its original branch from
        # Git's operation metadata rather than misreporting a missing worktree.
        elif entries.get("worktree") and "detached" in block.splitlines():
            path = entries["worktree"]
            gd = Path(git(path, "rev-parse", "--absolute-git-dir"))
            for operation in ("rebase-merge", "rebase-apply"):
                name = gd / operation / "head-name"
                if name.exists() and name.read_text().strip() == "refs/heads/" + record["branch"]:
                    record["path"] = path
                    return path
    raise RuntimeError("Registered branch has no resolvable worktree; re-register after a branch rename")


def ancestry(path, target):
    p = subprocess.run(["git", "merge-base", "--is-ancestor", target, "HEAD"], cwd=path, capture_output=True)
    if p.returncode not in (0, 1):
        raise RuntimeError("Cannot compare branch ancestry")
    return p.returncode == 0


def inspect(record):
    path = locate(record)
    git(path, "fetch", "--no-tags", "origin", "+refs/heads/" + record["target"] + ":refs/remotes/origin/" + record["target"])
    target = git(path, "rev-parse", "refs/remotes/origin/" + record["target"])
    gd = Path(git(path, "rev-parse", "--absolute-git-dir"))
    if git(path, "ls-files", "-u"):
        state = "Conflicts"
    elif (gd / "rebase-merge").exists() or (gd / "rebase-apply").exists() or (gd / "MERGE_HEAD").exists():
        state = "Syncing"
    elif record["state"] in ("Syncing", "Conflicts", "Verifying"):
        state = "Verifying"
    else:
        state = "Up to date" if ancestry(path, target) else "Needs sync"
    return state, target


def refresh(value=None):
    failed = False
    with registry() as data:
        if value and value not in data:
            raise RuntimeError("Issue is not registered")
        for url, record in data.items():
            if value and value != url:
                continue
            try:
                closed = gh("issue", "view", url, "--json", "state")["state"] == "CLOSED"
                if closed:
                    print(url + ": closed; skipped (use unregister to retire tracking)")
                    continue
                state, target = inspect(record)
                changed = state != record["state"] or target != record.get("observed")
                if changed:
                    set_field(url, "Branch sync", state)
                    if state == "Needs sync":
                        note(url, "Branch sync — Needs sync", "`" + record["branch"] + "` is behind `origin/" + record["target"] + "` at `" + target + "`. Request `/sync " + url + "` when ready.", "behind-" + target)
                record.update(state=state, observed=target, checked=now(), error=None)
                print(url + ": " + state)
            except (RuntimeError, OSError, subprocess.TimeoutExpired) as e:
                failed = True
                record.update(error=str(e), checked=now())
                # Do not erase a conflict or verification state on an offline check.
                if record["state"] not in ("Syncing", "Conflicts", "Verifying"):
                    try:
                        set_field(url, "Branch sync", "Unchecked")
                        record["state"] = "Unchecked"
                    except Exception:
                        pass
                print(url + ": " + str(e), file=sys.stderr)
    if failed:
        raise RuntimeError("Some checks failed; see local tracking status for details")


def sync_state(value, state, evidence=None):
    with registry() as data:
        if value not in data:
            if state == "Not started":
                set_field(value, "Branch sync", state)
                return
            raise RuntimeError("Register the issue's work branch first")
        record = data[value]
        if state == "Up to date":
            if not evidence:
                raise RuntimeError("Verification evidence file is required")
            body = Path(evidence).read_text().strip()
            if not body:
                raise RuntimeError("Verification evidence is empty")
            detected, target = inspect(record)
            path = record["path"]
            if detected in ("Conflicts", "Syncing") or not ancestry(path, target):
                raise RuntimeError("Sync incomplete or target moved; resolve and verify again")
            head = git(path, "rev-parse", "HEAD")
            note(value, "Sync verification", "HEAD: `" + head + "`\n\nTarget: `" + target + "`\n\n" + body, "verified-" + head + "-" + target)
            record["observed"] = target
        set_field(value, "Branch sync", state)
        record.update(state=state, checked=now())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("configure")
    sub.add_parser("list")
    link = sub.add_parser("link-orca")
    link.add_argument("issue")
    link.add_argument("--replace-existing", type=int)
    checkpoint = sub.add_parser("checkpoint-orca")
    checkpoint.add_argument("issue")
    checkpoint.add_argument("stage", choices=STATUSES)
    checkpoint.add_argument("--summary")
    for name in ("register", "unregister", "refresh", "status", "note", "sync-state", "add"):
        p = sub.add_parser(name)
        p.add_argument("issue", nargs="?" if name == "refresh" else None)
        if name == "status":
            p.add_argument("value", choices=STATUSES)
        if name == "sync-state":
            p.add_argument("value", choices=SYNC)
            p.add_argument("--evidence")
        if name == "note":
            p.add_argument("heading")
            p.add_argument("body_file")
            p.add_argument("--key")
    args = parser.parse_args()
    if args.command == "configure":
        configure()
        return
    if args.command == "list":
        with registry() as data:
            print(json.dumps(data, indent=2))
        return
    if args.command == "link-orca":
        result, exit_code = link_orca(args.issue, args.replace_existing)
        print(json.dumps(result, indent=2))
        return exit_code
    if args.command == "checkpoint-orca":
        result, exit_code = checkpoint_orca(args.issue, args.stage, args.summary)
        print(json.dumps(result, indent=2))
        return exit_code
    value = issue_url(args.issue) if args.issue else None
    if args.command == "add":
        item(value)
        print(value)
    elif args.command == "register":
        register(value)
    elif args.command == "unregister":
        with registry() as data:
            data.pop(value, None)
    elif args.command == "refresh":
        refresh(value)
    elif args.command == "status":
        result, exit_code = workflow_status(value, args.value)
        print(json.dumps(result, indent=2))
        return exit_code
    elif args.command == "sync-state":
        sync_state(value, args.value, args.evidence)
    elif args.command == "note":
        note(value, args.heading, Path(args.body_file).read_text(), args.key)


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as error:
        print("track: " + str(error), file=sys.stderr)
        sys.exit(1)
