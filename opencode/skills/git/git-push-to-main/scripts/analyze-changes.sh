#!/bin/bash
# Analyze git repository state for commit preparation
# Outputs: status, unpushed commits, staged/unstaged changes, recent commit style

set -e

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "ERROR: Not in a git repository"
    exit 1
fi

echo "=== GIT STATUS ==="
git status
echo ""

CURRENT_BRANCH=$(git branch --show-current)
echo "=== BRANCH ==="
echo "Current branch: $CURRENT_BRANCH"
echo ""

# Fetch so the behind-check below reflects reality, not a stale remote ref
echo "=== FETCHING ORIGIN ==="
git fetch origin --quiet 2>&1 || echo "WARNING: git fetch failed"
echo "(done)"
echo ""

# Behind the remote default branch? A bare 'git push' would be rejected.
echo "=== BEHIND origin/$CURRENT_BRANCH? ==="
BEHIND=0
if git rev-parse --verify --quiet "origin/$CURRENT_BRANCH" >/dev/null 2>&1; then
    BEHIND=$(git rev-list --count "HEAD..origin/$CURRENT_BRANCH" 2>/dev/null || echo "0")
    if [[ "$BEHIND" -gt 0 ]]; then
        echo "BLOCKER: behind origin/$CURRENT_BRANCH by $BEHIND commit(s)."
        echo "Someone else pushed. A plain 'git push' will be rejected."
        echo "Pull with --ff-only (or --rebase if you already have local commits) before pushing."
        echo ""
        echo "Incoming commits:"
        git log --oneline "HEAD..origin/$CURRENT_BRANCH"
    else
        echo "Up to date with origin/$CURRENT_BRANCH"
    fi
else
    echo "(no origin/$CURRENT_BRANCH yet)"
fi
echo ""

# Check for unpushed commits
echo "=== UNPUSHED COMMITS ==="
UPSTREAM=$(git rev-parse --abbrev-ref --symbolic-full-name @{u} 2>/dev/null || echo "")
if [[ -n "$UPSTREAM" ]]; then
    UNPUSHED=$(git rev-list --count @{u}..HEAD 2>/dev/null || echo "0")
    if [[ "$UNPUSHED" -gt 0 ]]; then
        echo "Found $UNPUSHED unpushed commit(s):"
        git log --oneline @{u}..HEAD
        echo ""
        echo "OPTIONS:"
        echo "  - Squash: Amend changes into existing commit(s)"
        echo "  - Stack: Add new commit on top"
    else
        echo "No unpushed commits (up to date with $UPSTREAM)"
    fi
else
    echo "No upstream branch configured"
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

# Check for README
echo "=== README CHECK ==="
if [[ -f "README.md" ]]; then
    echo "README.md exists"
    echo "Last modified: $(stat -f '%Sm' README.md 2>/dev/null || stat -c '%y' README.md 2>/dev/null)"
elif [[ -f "README" ]]; then
    echo "README exists (no .md extension)"
else
    echo "No README found"
fi
