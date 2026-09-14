#!/bin/bash
# Create a git commit with the given message
# Usage: create-commit.sh <message> [--amend]

set -e

if [[ -z "$1" ]]; then
    echo "Usage: $0 <message> [--amend]"
    echo ""
    echo "Options:"
    echo "  --amend    Amend the previous commit instead of creating new"
    exit 1
fi

MESSAGE="$1"
AMEND=""

if [[ "$2" == "--amend" ]]; then
    AMEND="--amend"
    echo "Amending previous commit..."
else
    echo "Creating new commit..."
fi

# Reject AI attribution in the commit message
FORBIDDEN_PATTERNS=(
    "Co-Authored-By"
    "Co-authored-by"
    "Generated with Claude Code"
    "Generated with \[Claude Code\]"
    "Claude Code <noreply@anthropic.com>"
)
for pattern in "${FORBIDDEN_PATTERNS[@]}"; do
    if echo "$MESSAGE" | grep -qi "$pattern"; then
        echo "ERROR: commit message contains forbidden attribution: '$pattern'"
        echo "Remove it and retry — no Claude Code attribution in git history."
        exit 1
    fi
done
if echo "$MESSAGE" | grep -q $'\xf0\x9f\xa4\x96'; then
    echo "ERROR: commit message contains robot emoji — no AI attribution in git history."
    exit 1
fi

# Check if there are staged changes
if git diff --cached --quiet; then
    echo "ERROR: No staged changes to commit"
    echo ""
    echo "Stage files first with:"
    echo "  git add <files>"
    echo "  or: bash \"$(dirname "$0")/stage-files.sh\" --all"
    exit 1
fi

# Create commit
git commit $AMEND -m "$MESSAGE"

echo ""
echo "=== COMMIT CREATED ==="
git log --oneline -1
echo ""
echo "=== CURRENT STATUS ==="
git status --short

# Show unpushed count
UPSTREAM=$(git rev-parse --abbrev-ref --symbolic-full-name @{u} 2>/dev/null || echo "")
if [[ -n "$UPSTREAM" ]]; then
    UNPUSHED=$(git rev-list --count @{u}..HEAD 2>/dev/null || echo "0")
    echo ""
    echo "You have $UNPUSHED unpushed commit(s). Push when ready with: git push"
fi
