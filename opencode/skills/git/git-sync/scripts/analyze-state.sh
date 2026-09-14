#!/bin/bash
# Analyze git state before syncing main into a feature branch
# Outputs: current branch, default branch, uncommitted summary, main divergence, merge state

set -e

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "ERROR: Not in a git repository"
    exit 1
fi

source "$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../../_lib/worktree.sh"

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
    echo "ERROR: Currently on the default branch ($DEFAULT_BRANCH)."
    echo "This skill is for syncing main INTO a feature branch."
    echo "Use git-push-to-main or git-branch-and-pr instead."
    exit 2
fi

# Merge-in-progress check
echo "=== MERGE STATE ==="
if [[ -f "$(git rev-parse --git-dir)/MERGE_HEAD" ]]; then
    echo "ERROR: A merge is already in progress."
    echo "Finish it (git merge --continue) or abort it (git merge --abort) before running this skill."
    exit 3
else
    echo "(no merge in progress)"
fi
echo ""

# Uncommitted summary
echo "=== UNCOMMITTED CHANGES ==="
PORCELAIN=$(git status --porcelain)
if [[ -n "$PORCELAIN" ]]; then
    echo "$PORCELAIN"
    echo ""
    echo "(will be stashed before sync, restored after)"
else
    echo "(no uncommitted changes — skill will just sync main into branch, no final commit)"
fi
echo ""

# Fetch to update remote refs for divergence comparison
echo "=== FETCHING ORIGIN ==="
git fetch origin --quiet 2>&1 || echo "WARNING: git fetch failed"
echo "(done)"
echo ""

# Local default vs origin default
#
# This only matters because sync-main.sh wants to fast-forward the local default branch.
# When that branch lives in ANOTHER worktree (Orca ADE), its state is not this branch's
# business and sync-main.sh will leave it alone — so report it and carry on rather than
# refusing to sync. Integration targets origin/<default> either way.
echo "=== LOCAL $DEFAULT_BRANCH vs origin/$DEFAULT_BRANCH ==="
DEFAULT_HELD_AT=$(branch_checked_out_elsewhere "$DEFAULT_BRANCH")
if [[ -n "$DEFAULT_HELD_AT" ]]; then
    echo "Local $DEFAULT_BRANCH is checked out in another worktree: $DEFAULT_HELD_AT"
    echo "It will not be touched. Integration target is origin/$DEFAULT_BRANCH."
    if git show-ref --verify --quiet "refs/heads/$DEFAULT_BRANCH"; then
        AHEAD=$(git rev-list --count "origin/$DEFAULT_BRANCH..$DEFAULT_BRANCH" 2>/dev/null || echo "0")
        BEHIND=$(git rev-list --count "$DEFAULT_BRANCH..origin/$DEFAULT_BRANCH" 2>/dev/null || echo "0")
        echo "(That worktree's $DEFAULT_BRANCH is ahead $AHEAD, behind $BEHIND — informational only.)"
    fi
elif git show-ref --verify --quiet "refs/heads/$DEFAULT_BRANCH"; then
    LOCAL_DEFAULT=$(git rev-parse "$DEFAULT_BRANCH")
    REMOTE_DEFAULT=$(git rev-parse "origin/$DEFAULT_BRANCH" 2>/dev/null || echo "")
    if [[ -z "$REMOTE_DEFAULT" ]]; then
        echo "WARNING: origin/$DEFAULT_BRANCH not found"
    elif [[ "$LOCAL_DEFAULT" == "$REMOTE_DEFAULT" ]]; then
        echo "Local $DEFAULT_BRANCH is up to date with origin/$DEFAULT_BRANCH"
    else
        AHEAD=$(git rev-list --count "origin/$DEFAULT_BRANCH..$DEFAULT_BRANCH" 2>/dev/null || echo "0")
        BEHIND=$(git rev-list --count "$DEFAULT_BRANCH..origin/$DEFAULT_BRANCH" 2>/dev/null || echo "0")
        echo "Ahead: $AHEAD, Behind: $BEHIND"
        if [[ "$AHEAD" -gt 0 && "$BEHIND" -gt 0 ]]; then
            echo "ERROR: Local $DEFAULT_BRANCH has diverged from origin/$DEFAULT_BRANCH."
            echo "Push or rebase your local $DEFAULT_BRANCH first. This skill will not overwrite your commits."
            exit 4
        elif [[ "$AHEAD" -gt 0 ]]; then
            echo "ERROR: Local $DEFAULT_BRANCH has $AHEAD unpushed commit(s)."
            echo "Push them first. This skill will not overwrite your commits."
            exit 4
        else
            echo "Local $DEFAULT_BRANCH is behind by $BEHIND commit(s) — will fast-forward."
        fi
    fi
else
    echo "No local $DEFAULT_BRANCH branch — will create it from origin/$DEFAULT_BRANCH"
fi
echo ""

# Feature branch upstream
echo "=== FEATURE BRANCH UPSTREAM ==="
UPSTREAM=$(git rev-parse --abbrev-ref --symbolic-full-name @{u} 2>/dev/null || echo "")
if [[ -n "$UPSTREAM" ]]; then
    echo "Upstream: $UPSTREAM"
else
    echo "(no upstream — first push will need 'git push -u origin $CURRENT_BRANCH')"
fi
echo ""

# Rebase eligibility — a rebase gives linear history, but it rewrites SHAs.
# Anything that makes that rewrite expensive or dangerous disqualifies it.
echo "=== REBASE ELIGIBILITY ==="
DISQUALIFIED=""
ASK=""

if [[ -n "$UPSTREAM" ]]; then
    PUSHED=$(git rev-list --count "$UPSTREAM" 2>/dev/null || echo "0")
    if [[ "$PUSHED" -gt 0 ]]; then
        PR_STATE=$(gh pr view "$CURRENT_BRANCH" --json state --jq '.state' 2>/dev/null || echo "")
        if [[ "$PR_STATE" == "OPEN" ]]; then
            DISQUALIFIED="branch is pushed AND has an open PR — a rebase needs a force-push, which can orphan review comments pinned to the old SHAs"
        else
            ASK="branch is already pushed — a rebase would need 'git push --force-with-lease'"
        fi
    fi
fi

MERGE_COMMITS=$(git log --merges --oneline "origin/$DEFAULT_BRANCH..HEAD" 2>/dev/null || echo "")
if [[ -n "$MERGE_COMMITS" ]]; then
    echo "Branch already contains merge commit(s):"
    echo "$MERGE_COMMITS"
    DISQUALIFIED="branch already contains a merge commit — rebase flattens or chokes on it"
fi

if [[ -n "$DISQUALIFIED" ]]; then
    echo "VERDICT: MERGE — $DISQUALIFIED"
elif [[ -n "$ASK" ]]; then
    echo "VERDICT: ASK USER — $ASK"
else
    echo "VERDICT: REBASE — branch is local-only with no merge commits"
fi
echo ""

# Recent commits for style reference
echo "=== RECENT COMMITS (for style reference) ==="
git log --oneline -5 2>/dev/null || echo "(no commits yet)"
