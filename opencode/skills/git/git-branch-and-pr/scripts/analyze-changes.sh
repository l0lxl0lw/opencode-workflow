#!/bin/bash
# Analyze git repository state for commit and PR preparation
# Outputs: status, branch info, diffs, recent commits, PR template check

set -e

source "$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../../_lib/repo-checks.sh"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "ERROR: Not in a git repository"
    exit 1
fi

echo "=== GIT STATUS ==="
git status
echo ""

# Branch info
echo "=== BRANCH INFO ==="
CURRENT_BRANCH=$(git branch --show-current)
echo "Current branch: $CURRENT_BRANCH"

# Detect default branch
DEFAULT_BRANCH=$(gh repo view --json defaultBranchRef --jq '.defaultBranchRef.name' 2>/dev/null || echo "")
if [[ -z "$DEFAULT_BRANCH" ]]; then
    # Fallback: check common names
    if git show-ref --verify --quiet refs/heads/main 2>/dev/null; then
        DEFAULT_BRANCH="main"
    elif git show-ref --verify --quiet refs/heads/master 2>/dev/null; then
        DEFAULT_BRANCH="master"
    else
        DEFAULT_BRANCH="main"
    fi
fi
echo "Default branch: $DEFAULT_BRANCH"

if [[ "$CURRENT_BRANCH" == "$DEFAULT_BRANCH" ]]; then
    echo "WARNING: Currently on the default branch — a feature branch will need to be created"
fi
echo ""

# Staged changes
echo "=== STAGED CHANGES (git diff --cached) ==="
STAGED=$(git diff --cached --stat)
if [[ -n "$STAGED" ]]; then
    echo "$STAGED"
    echo ""
    echo "--- Staged diff ---"
    git diff --cached
else
    echo "(no staged changes)"
fi
echo ""

# Unstaged changes
echo "=== UNSTAGED CHANGES (git diff) ==="
UNSTAGED=$(git diff --stat)
if [[ -n "$UNSTAGED" ]]; then
    echo "$UNSTAGED"
    echo ""
    echo "--- Unstaged diff ---"
    git diff
else
    echo "(no unstaged changes)"
fi
echo ""

# Untracked files
echo "=== UNTRACKED FILES ==="
UNTRACKED=$(git ls-files --others --exclude-standard)
if [[ -n "$UNTRACKED" ]]; then
    echo "$UNTRACKED"
else
    echo "(no untracked files)"
fi
echo ""

# Recent commits for style reference
echo "=== RECENT COMMITS (for style reference) ==="
git log --oneline -5 2>/dev/null || echo "(no commits yet)"
echo ""

# If on a feature branch, show commits ahead of default
if [[ "$CURRENT_BRANCH" != "$DEFAULT_BRANCH" ]]; then
    echo "=== COMMITS AHEAD OF $DEFAULT_BRANCH ==="
    MERGE_BASE=$(git merge-base "$DEFAULT_BRANCH" HEAD 2>/dev/null || echo "")
    if [[ -n "$MERGE_BASE" ]]; then
        git log --oneline "$MERGE_BASE"..HEAD 2>/dev/null || echo "(none)"
    else
        echo "(could not determine merge base)"
    fi
    echo ""
fi

# Check for README
echo "=== README CHECK ==="
if [[ -f "README.md" ]]; then
    echo "README.md exists"
elif [[ -f "README" ]]; then
    echo "README exists (no .md extension)"
else
    echo "No README found"
fi
echo ""

# Repo-local pre-PR checks
# Invariants this repo declares for itself (spec drift, stale generated artifacts).
# This skill runs on the default branch with the work still uncommitted, so the
# relevant file set is the working tree — staged, unstaged and untracked.
CHANGED_FILES=$(mktemp)
repo_check_worktree_files | sed '/^$/d' | sort -u > "$CHANGED_FILES"
emit_repo_checks_section "$CHANGED_FILES" "git-branch-and-pr" "$DEFAULT_BRANCH" || true
rm -f "$CHANGED_FILES"
echo ""

# Check for PR template
echo "=== PR TEMPLATE CHECK ==="
if [[ -f ".github/pull_request_template.md" ]]; then
    echo "PR template found: .github/pull_request_template.md"
elif [[ -f ".github/PULL_REQUEST_TEMPLATE.md" ]]; then
    echo "PR template found: .github/PULL_REQUEST_TEMPLATE.md"
elif [[ -f "docs/pull_request_template.md" ]]; then
    echo "PR template found: docs/pull_request_template.md"
else
    echo "No PR template found (will use default format)"
fi
