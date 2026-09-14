#!/bin/bash
# Verify the PR for the current branch is genuinely MERGED.
#
# This is the hard gate for git-cleanup. Deleting a branch whose work
# is NOT on the default branch is data loss — the commits become unreachable.
# Nothing destructive may run until this script exits 0.
#
# Usage: verify-merged.sh
# Exit:  0  MERGED — safe to clean up
#        1  error (not a repo, no gh, gh not authenticated)
#        2  on the default branch — nothing to clean up
#        3  no PR found for this branch
#        4  PR still OPEN
#        5  PR CLOSED without merging
#        6  dirty working tree

set -e

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "ERROR: Not in a git repository"
    exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
    echo "ERROR: gh CLI not found."
    echo "This skill needs gh to verify merge state authoritatively."
    echo "Without that check, deleting the branch risks losing unmerged work."
    exit 1
fi

CURRENT_BRANCH=$(git branch --show-current)
echo "=== CURRENT BRANCH ==="
echo "$CURRENT_BRANCH"
echo ""

# Detect default branch
DEFAULT_BRANCH=$(gh repo view --json defaultBranchRef --jq '.defaultBranchRef.name' 2>/dev/null || echo "")
if [[ -z "$DEFAULT_BRANCH" ]]; then
    if git show-ref --verify --quiet refs/heads/main 2>/dev/null; then
        DEFAULT_BRANCH="main"
    elif git show-ref --verify --quiet refs/heads/master 2>/dev/null; then
        DEFAULT_BRANCH="master"
    else
        DEFAULT_BRANCH="main"
    fi
fi
echo "=== DEFAULT BRANCH ==="
echo "$DEFAULT_BRANCH"
echo ""

if [[ "$CURRENT_BRANCH" == "$DEFAULT_BRANCH" ]]; then
    echo "ERROR: Already on the default branch ($DEFAULT_BRANCH). Nothing to clean up."
    echo "This skill deletes the feature branch you are standing on after its PR merged."
    exit 2
fi

# The gate. gh is authoritative — the local commit graph is NOT.
# After a squash or rebase merge the branch commits are not ancestors of the
# default branch, so the local graph looks unmerged even though the PR merged.
echo "=== PR MERGE STATE ==="
PR_INFO=$(gh pr view "$CURRENT_BRANCH" \
    --json number,state,mergedAt,url \
    --jq '[.number, .state, (.mergedAt // "null"), .url] | @tsv' 2>/dev/null || echo "")

if [[ -z "$PR_INFO" ]]; then
    echo "ERROR: gh reports no PR for branch '$CURRENT_BRANCH'."
    echo "Do NOT assume it merged. Nothing has been deleted."
    exit 3
fi

IFS=$'\t' read -r PR_NUMBER PR_STATE PR_MERGED_AT PR_URL <<< "$PR_INFO"
echo "PR:        #$PR_NUMBER"
echo "State:     $PR_STATE"
echo "mergedAt:  $PR_MERGED_AT"
echo "URL:       $PR_URL"
echo ""

if [[ "$PR_STATE" == "OPEN" ]]; then
    echo "STOP: PR #$PR_NUMBER is still OPEN — it was never merged."
    echo "Deleting this branch would throw away the only copy of the work."
    exit 4
fi

if [[ "$PR_STATE" != "MERGED" || "$PR_MERGED_AT" == "null" ]]; then
    echo "STOP: PR #$PR_NUMBER is $PR_STATE and mergedAt is $PR_MERGED_AT."
    echo "The PR was closed WITHOUT merging — this branch's work is NOT on $DEFAULT_BRANCH."
    echo "Deleting the branch loses it. Require explicit user confirmation before anything destructive."
    exit 5
fi

echo "CONFIRMED MERGED at $PR_MERGED_AT — the work is on $DEFAULT_BRANCH."
echo ""

# Only now is a dirty tree worth reporting: switching branches would tangle it.
echo "=== WORKING TREE ==="
PORCELAIN=$(git status --porcelain)
if [[ -n "$PORCELAIN" ]]; then
    echo "$PORCELAIN"
    echo ""
    echo "STOP: working tree is dirty. Switching branches and pulling would tangle this work."
    echo "Ask the user to commit or stash first. Do not stash on their behalf."
    exit 6
fi
echo "(clean)"
echo ""

echo "=== SAFE TO CLEAN UP ==="
echo "branch=$CURRENT_BRANCH"
echo "default=$DEFAULT_BRANCH"
echo "pr=$PR_NUMBER"
echo "url=$PR_URL"
