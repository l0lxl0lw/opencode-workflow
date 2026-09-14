#!/bin/bash
# Prove no conflict markers survive before committing or continuing a rebase.
#
# Two independent checks, because neither alone is sufficient:
#   - git diff --check       catches markers in what is staged/unstaged vs HEAD
#   - a content grep         catches markers already staged, or in untracked files
#
# Usage: verify-resolution.sh [--quiet]
# Exit:  0  clean — no markers, no unmerged paths
#        1  markers or unmerged paths remain

QUIET=""
[[ "$1" == "--quiet" ]] && QUIET=1

FAILED=0

# Unmerged paths still in the index
UNMERGED=$(git diff --name-only --diff-filter=U 2>/dev/null)
if [[ -n "$UNMERGED" ]]; then
    FAILED=1
    if [[ -z "$QUIET" ]]; then
        echo "=== UNMERGED PATHS ==="
        echo "$UNMERGED"
        echo ""
    fi
fi

# git's own marker detector
CHECK=$(git diff --check 2>/dev/null)
if [[ -n "$CHECK" ]]; then
    FAILED=1
    if [[ -z "$QUIET" ]]; then
        echo "=== git diff --check ==="
        echo "$CHECK"
        echo ""
    fi
fi

# Content grep for the three marker lines at column 0. Markdown is excluded
# because documentation about conflicts legitimately contains them.
MARKERS=$(git grep -nE '^(<<<<<<< |=======$|>>>>>>> )' -- . 2>/dev/null | grep -v '\.md:' || true)
if [[ -n "$MARKERS" ]]; then
    FAILED=1
    if [[ -z "$QUIET" ]]; then
        echo "=== LEFTOVER CONFLICT MARKERS ==="
        echo "$MARKERS"
        echo ""
    fi
fi

if [[ $FAILED -eq 1 ]]; then
    [[ -z "$QUIET" ]] && echo "RESULT: markers or unmerged paths remain — do NOT commit."
    exit 1
fi

[[ -z "$QUIET" ]] && echo "RESULT: clean — no conflict markers, no unmerged paths."
exit 0
