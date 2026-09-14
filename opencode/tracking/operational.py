"""Recognize only exact machine-generated branch observations, never free prose."""
import hashlib
import json
import re

MARKER = re.compile(r"<!-- opencode-operational:v1 (\{[^\n]*\}) -->")
REF = r"[A-Za-z0-9._/@+\-]+"
ISSUE = r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/issues/\d+"


def known(prefix, issue=None):
    branch = re.fullmatch(r"## Branch tracking\n\nBranch: `(" + REF + r")`\n\nTarget: `origin/(" + REF +
        r")`\n\nAutomatic detection; sync requires an explicit request\.\n\n<!-- opencode-track:register-(" + REF + r") -->", prefix)
    if branch:
        return branch[1] == branch[3]
    behind = re.fullmatch(r"## Branch sync — Needs sync\n\n`(" + REF + r")` is behind `origin/(" + REF +
        r")` at `([0-9a-f]{40,64})`\. Request `/sync (" + ISSUE + r")` when ready\.\n\n<!-- opencode-track:behind-([0-9a-f]{40,64}) -->", prefix)
    return bool(behind and behind[3] == behind[5] and (issue is None or behind[4] == issue))


def wrap(prefix):
    if not known(prefix):
        return prefix
    marker = {"kind": "branch-observation", "body_sha256": hashlib.sha256(prefix.encode()).hexdigest()}
    return prefix + "\n\n<!-- opencode-operational:v1 " + json.dumps(marker, sort_keys=True) + " -->"


def valid(comment):
    body = comment.get("body", "")
    matches = list(MARKER.finditer(body))
    if len(matches) != 1 or body[matches[0].end():].strip():
        return False
    prefix = body[:matches[0].start()].strip()
    try:
        meta = json.loads(matches[0][1])
        return (meta.get("kind") == "branch-observation" and
                meta.get("body_sha256") == hashlib.sha256(prefix.encode()).hexdigest() and
                known(prefix, comment.get("html_url", "").split("#")[0]))
    except (ValueError, TypeError):
        return False
