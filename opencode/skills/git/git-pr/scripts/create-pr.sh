#!/bin/bash
# Push the current branch and open a PR against the default branch.
# Rejects AI attribution in the title and body, and refuses to create a duplicate PR.
#
# Usage: create-pr.sh <title> <body_file> [--draft]
# Exit:  0  PR created
#        1  usage / validation error
#        2  a PR already exists for this branch (its URL is printed)

set -e

TITLE="$1"
BODY_FILE="$2"
DRAFT_FLAG=""

if [[ -z "$TITLE" || -z "$BODY_FILE" ]]; then
    echo "Usage: $0 <title> <body_file> [--draft]"
    echo ""
    echo "Write the PR body to a file first, then pass its path."
    exit 1
fi

if [[ ! -f "$BODY_FILE" ]]; then
    echo "ERROR: body file not found: $BODY_FILE"
    exit 1
fi

if [[ "$3" == "--draft" ]]; then
    DRAFT_FLAG="--draft"
fi

if ! command -v gh >/dev/null 2>&1; then
    echo "ERROR: gh CLI not found"
    exit 1
fi

BODY=$(cat "$BODY_FILE")

# Reject AI attribution in BOTH the title and the body. The commit script enforces
# this for commit messages; the same rule applies to anything published to GitHub.
FORBIDDEN_PATTERNS=(
    "Co-Authored-By"
    "Co-authored-by"
    "Generated with Claude Code"
    "Generated with \[Claude Code\]"
    "Claude Code <noreply@anthropic.com>"
    "claude.com/claude-code"
    "claude.ai/code"
)
for pattern in "${FORBIDDEN_PATTERNS[@]}"; do
    if echo "$TITLE$BODY" | grep -qi "$pattern"; then
        echo "ERROR: PR title/body contains forbidden attribution: '$pattern'"
        echo "Remove it and retry — no Claude Code attribution on GitHub."
        exit 1
    fi
done
if echo "$TITLE$BODY" | grep -q $'\xf0\x9f\xa4\x96'; then
    echo "ERROR: PR title/body contains robot emoji — no AI attribution on GitHub."
    exit 1
fi

CURRENT_BRANCH=$(git branch --show-current)

DEFAULT_BRANCH=$(gh repo view --json defaultBranchRef --jq '.defaultBranchRef.name' 2>/dev/null || echo "")
if [[ -z "$DEFAULT_BRANCH" ]]; then
    if git show-ref --verify --quiet refs/heads/main 2>/dev/null; then
        DEFAULT_BRANCH="main"
    else
        DEFAULT_BRANCH="master"
    fi
fi

if [[ "$CURRENT_BRANCH" == "$DEFAULT_BRANCH" ]]; then
    echo "ERROR: on the default branch ($DEFAULT_BRANCH) — refusing to PR it into itself"
    exit 1
fi

# Never create a duplicate — this skill must be safe to re-run.
EXISTING=$(gh pr view "$CURRENT_BRANCH" --json number,state,url \
    --jq '[.number, .state, .url] | @tsv' 2>/dev/null || echo "")
if [[ -n "$EXISTING" ]]; then
    IFS=$'\t' read -r E_NUM E_STATE E_URL <<< "$EXISTING"
    echo "A PR already exists for '$CURRENT_BRANCH': #$E_NUM ($E_STATE)"
    echo "$E_URL"
    echo ""
    echo "Not creating a duplicate. Update the existing PR body with:"
    echo "  gh pr edit $E_NUM --body-file $BODY_FILE"
    exit 2
fi

# Uncommitted work would silently not be in the PR.
if [[ -n "$(git status --porcelain)" ]]; then
    echo "ERROR: working tree is dirty — this work would not be in the PR:"
    git status --short
    exit 1
fi

echo "=== Pushing $CURRENT_BRANCH ==="
if git rev-parse --abbrev-ref --symbolic-full-name @{u} >/dev/null 2>&1; then
    git push
else
    git push -u origin "$CURRENT_BRANCH"
fi

echo ""
echo "=== Creating PR against $DEFAULT_BRANCH ==="
gh pr create \
    --base "$DEFAULT_BRANCH" \
    --title "$TITLE" \
    --body-file "$BODY_FILE" \
    $DRAFT_FLAG

echo ""
echo "=== PR CREATED ==="
gh pr view --json url --jq '.url'
