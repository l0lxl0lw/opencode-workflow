#!/bin/bash
# Decide whether the PR for the current branch is actually ready to merge.
# Read-only — this script never merges anything.
#
# Usage: check-mergeable.sh
# Exit:  0  ready to merge
#        1  error (not a repo, no gh)
#        2  on the default branch — no PR to merge
#        3  no PR for this branch
#        4  PR is not OPEN (already merged, or closed)
#        5  PR is a draft
#        6  PR has conflicts / is not mergeable
#        7  CI checks failing or still pending
#        8  blocked by branch protection (review required, etc.)

set -e

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "ERROR: Not in a git repository"
    exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
    echo "ERROR: gh CLI not found — cannot inspect or merge a PR"
    exit 1
fi

CURRENT_BRANCH=$(git branch --show-current)
DEFAULT_BRANCH=$(gh repo view --json defaultBranchRef --jq '.defaultBranchRef.name' 2>/dev/null || echo "main")

echo "=== BRANCH ==="
echo "Current: $CURRENT_BRANCH"
echo "Default: $DEFAULT_BRANCH"
echo ""

if [[ "$CURRENT_BRANCH" == "$DEFAULT_BRANCH" ]]; then
    echo "ERROR: on the default branch — there is no PR here to merge."
    exit 2
fi

PR=$(gh pr view "$CURRENT_BRANCH" \
    --json number,state,url,title,isDraft,mergeable,mergeStateStatus,reviewDecision \
    --jq '[.number, .state, .url, .title, (.isDraft|tostring), .mergeable, .mergeStateStatus, (.reviewDecision // "NONE")] | @tsv' \
    2>/dev/null || echo "")

if [[ -z "$PR" ]]; then
    echo "ERROR: no PR found for branch '$CURRENT_BRANCH'."
    echo "Open one first with git-pr."
    exit 3
fi

IFS=$'\t' read -r P_NUM P_STATE P_URL P_TITLE P_DRAFT P_MERGEABLE P_MERGESTATE P_REVIEW <<< "$PR"

echo "=== PR ==="
echo "#$P_NUM  $P_TITLE"
echo "$P_URL"
echo "State:        $P_STATE"
echo "Draft:        $P_DRAFT"
echo "Mergeable:    $P_MERGEABLE"
echo "Merge state:  $P_MERGESTATE"
echo "Review:       $P_REVIEW"
echo ""

if [[ "$P_STATE" == "MERGED" ]]; then
    echo "Already MERGED. Nothing to do here — run git-cleanup to delete the branch."
    exit 4
fi
if [[ "$P_STATE" != "OPEN" ]]; then
    echo "ERROR: PR is $P_STATE, not OPEN. It cannot be merged."
    exit 4
fi

if [[ "$P_DRAFT" == "true" ]]; then
    echo "STOP: PR #$P_NUM is a draft."
    echo "Mark it ready first: gh pr ready $P_NUM"
    exit 5
fi

if [[ "$P_MERGEABLE" == "CONFLICTING" ]]; then
    echo "STOP: PR has conflicts with $DEFAULT_BRANCH."
    echo "Run git-sync on the branch to resolve them, push, then retry."
    exit 6
fi

if [[ "$P_MERGESTATE" == "DIRTY" ]]; then
    echo "STOP: merge state is DIRTY — conflicts must be resolved first."
    echo "Run git-sync on the branch, push, then retry."
    exit 6
fi

if [[ "$P_MERGESTATE" == "BEHIND" ]]; then
    echo "NOTE: branch is BEHIND $DEFAULT_BRANCH and the repo requires branches to be up to date."
    echo "Run git-sync on the branch and push before merging."
    exit 6
fi

echo "=== CI CHECKS ==="
set +e
CHECKS_OUT=$(gh pr checks "$P_NUM" 2>&1)
CHECKS_RC=$?
set -e
echo "$CHECKS_OUT"
echo ""

# gh pr checks: 0 = all passed, 8 = still pending, 1 = failing (or none configured)
if [[ $CHECKS_RC -eq 8 ]]; then
    echo "STOP: CI checks are still running. Wait for them, or watch with:"
    echo "  gh pr checks $P_NUM --watch"
    exit 7
fi
if [[ $CHECKS_RC -ne 0 ]]; then
    if echo "$CHECKS_OUT" | grep -qi "no checks"; then
        echo "NOTE: this repo reports no CI checks for the PR."
    else
        echo "STOP: CI checks are failing. Fix them and push (git-push-branch), then retry."
        exit 7
    fi
fi

if [[ "$P_MERGESTATE" == "BLOCKED" ]]; then
    echo "STOP: merge is BLOCKED by branch protection (review decision: $P_REVIEW)."
    echo "A required review or status is missing. Do not bypass this."
    exit 8
fi

echo "=== READY TO MERGE ==="
echo "pr=$P_NUM"
echo "url=$P_URL"
echo "branch=$CURRENT_BRANCH"
echo "default=$DEFAULT_BRANCH"
