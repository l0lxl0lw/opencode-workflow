#!/bin/bash
# Stage files for commit, with safety checks
# Usage: stage-files.sh [files...] or stage-files.sh --all

set -e

if [[ "$1" == "--all" ]]; then
    # Stage all changes but warn about sensitive files
    echo "=== Checking for sensitive files ==="
    SENSITIVE=$(git status --porcelain | grep -E '\.(env|pem|key|secret|credentials|token)' || true)
    if [[ -n "$SENSITIVE" ]]; then
        echo "WARNING: Potentially sensitive files detected:"
        echo "$SENSITIVE"
        echo ""
        echo "These files will NOT be staged automatically."
        echo "Stage them manually if intended: git add <file>"
        echo ""
        # Stage everything except sensitive patterns
        git add --all
        git reset HEAD -- '*.env' '*.pem' '*.key' '*.secret' '*.credentials' '*.token' '.env*' 2>/dev/null || true
    else
        git add --all
    fi
elif [[ $# -eq 0 ]]; then
    echo "Usage: $0 [files...] or $0 --all"
    echo ""
    echo "Current unstaged/untracked files:"
    git status --short
    exit 1
else
    # Stage specific files
    git add "$@"
fi

echo ""
echo "=== STAGED FILES ==="
git diff --cached --stat
