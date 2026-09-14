#!/bin/bash
# Merge the PR for the current branch with an explicit strategy.
#
# Run check-mergeable.sh first and confirm it exited 0. This script does not
# delete anything — hand off to git-cleanup afterwards so the local branch is
# deleted behind a verified MERGED state and the default branch is refreshed.
#
# Usage: merge-pr.sh <pr_number> <squash|merge|rebase>
# Exit:  0  merged
#        1  usage / error

set -e

PR_NUM="$1"
STRATEGY="$2"

if [[ -z "$PR_NUM" || -z "$STRATEGY" ]]; then
    echo "Usage: $0 <pr_number> <squash|merge|rebase>"
    exit 1
fi

case "$STRATEGY" in
    squash) FLAG="--squash" ;;
    merge)  FLAG="--merge" ;;
    rebase) FLAG="--rebase" ;;
    *)
        echo "ERROR: unknown strategy '$STRATEGY' (expected squash, merge or rebase)"
        exit 1
        ;;
esac

if ! command -v gh >/dev/null 2>&1; then
    echo "ERROR: gh CLI not found"
    exit 1
fi

# Re-confirm the PR is still OPEN — someone may have merged or closed it since
# the check ran, and gh pr merge on a stale assumption is confusing to debug.
STATE=$(gh pr view "$PR_NUM" --json state --jq '.state' 2>/dev/null || echo "")
if [[ "$STATE" != "OPEN" ]]; then
    echo "ERROR: PR #$PR_NUM is $STATE, not OPEN. Refusing to merge."
    exit 1
fi

echo "=== Merging PR #$PR_NUM with --$STRATEGY ==="
# Deliberately NOT passing --delete-branch: git-cleanup deletes the branch behind
# its own verified-MERGED gate and refreshes the default branch at the same time.
# Deliberately NOT passing --admin: bypassing branch protection is never automatic.
gh pr merge "$PR_NUM" $FLAG

echo ""
echo "=== MERGED ==="
gh pr view "$PR_NUM" --json number,state,mergedAt,url \
    --jq '"PR #\(.number) \(.state) at \(.mergedAt)\n\(.url)"'

echo ""
echo "Next: run git-cleanup to delete the branch and refresh the default branch."
