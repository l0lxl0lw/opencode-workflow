#!/bin/bash
# Fetch origin and bring the local default branch up to date WITHOUT checking it out.
# Usage: sync-main.sh <default_branch> <feature_branch>
#
# Exit 0  ready to integrate against origin/<default>
# Exit 1  bad usage
# Exit 2  local <default> has diverged from origin and could not be fast-forwarded
#
# This never runs `git checkout`. A repo can have several checkouts (git worktrees, as
# Orca ADE uses), and git refuses to check out a branch already checked out elsewhere —
# so the old switch-to-default-and-back dance died with
#   fatal: 'main' is already used by worktree at '<path>'
# in every linked worktree. It was also unnecessary: the integration target for a
# feature branch is `origin/<default>`, never the local branch.

set -e

DEFAULT_BRANCH="$1"
FEATURE_BRANCH="$2"

if [[ -z "$DEFAULT_BRANCH" || -z "$FEATURE_BRANCH" ]]; then
    echo "Usage: $0 <default_branch> <feature_branch>"
    exit 1
fi

if [[ "$DEFAULT_BRANCH" == "$FEATURE_BRANCH" ]]; then
    echo "ERROR: default branch and feature branch are the same ($DEFAULT_BRANCH)"
    exit 1
fi

source "$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../../_lib/worktree.sh"

echo "=== Fetching origin ==="
git fetch origin

if ! git rev-parse --verify --quiet "origin/$DEFAULT_BRANCH" >/dev/null; then
    echo "ERROR: origin/$DEFAULT_BRANCH does not exist."
    exit 1
fi

echo ""
echo "=== Updating local $DEFAULT_BRANCH (ref only, no checkout) ==="
set +e
fast_forward_default_ref "$DEFAULT_BRANCH"
FF_STATUS=$?
set -e

if [[ $FF_STATUS -eq 2 ]]; then
    echo ""
    echo "ERROR: local $DEFAULT_BRANCH has diverged from origin/$DEFAULT_BRANCH."
    echo "Push or rebase your local $DEFAULT_BRANCH first — this script will not overwrite it."
    exit 2
fi

if is_linked_worktree; then
    echo ""
    echo "=== Linked worktree ==="
    echo "This checkout is a linked worktree; the main checkout is untouched."
fi

echo ""
echo "=== Ready. Integration target is origin/$DEFAULT_BRANCH ==="
echo "Still on: $(git branch --show-current)"
git log --oneline -1 "origin/$DEFAULT_BRANCH"
