#!/bin/bash
# Analyze a feature branch before committing and pushing to it.
# Covers the everyday loop: make a change, commit it, push it to the open PR.
#
# Usage: analyze-branch.sh
# Exit:  0  ready
#        1  error (not a repo)
#        2  on the default branch — wrong skill
#        3  nothing to commit and nothing to push

set -e

source "$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../../_lib/repo-checks.sh"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "ERROR: Not in a git repository"
    exit 1
fi

echo "=== BRANCH INFO ==="
CURRENT_BRANCH=$(git branch --show-current)
echo "Current branch: $CURRENT_BRANCH"

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
echo "Default branch: $DEFAULT_BRANCH"
echo ""

if [[ "$CURRENT_BRANCH" == "$DEFAULT_BRANCH" ]]; then
    echo "ERROR: On the default branch ($DEFAULT_BRANCH)."
    echo "Use git-push-to-main to commit and push there."
    exit 2
fi

echo "=== GIT STATUS ==="
git status --short
echo ""

echo "=== STAGED CHANGES ==="
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

echo "=== UNSTAGED CHANGES ==="
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

echo "=== UNTRACKED FILES ==="
UNTRACKED=$(git ls-files --others --exclude-standard)
if [[ -n "$UNTRACKED" ]]; then
    echo "$UNTRACKED"
else
    echo "(no untracked files)"
fi
echo ""

echo "=== FETCHING ORIGIN ==="
git fetch origin --quiet 2>&1 || echo "WARNING: git fetch failed"
echo "(done)"
echo ""

echo "=== UPSTREAM / UNPUSHED ==="
UPSTREAM=$(git rev-parse --abbrev-ref --symbolic-full-name @{u} 2>/dev/null || echo "")
UNPUSHED_COUNT=0
if [[ -n "$UPSTREAM" ]]; then
    UNPUSHED_COUNT=$(git rev-list --count @{u}..HEAD 2>/dev/null || echo "0")
    echo "Upstream: $UPSTREAM"
    echo "Unpushed commits: $UNPUSHED_COUNT"
    if [[ "$UNPUSHED_COUNT" -gt 0 ]]; then
        git log --oneline @{u}..HEAD
    fi
    # A branch behind its own upstream means someone else pushed to it
    BEHIND_UPSTREAM=$(git rev-list --count HEAD..@{u} 2>/dev/null || echo "0")
    if [[ "$BEHIND_UPSTREAM" -gt 0 ]]; then
        echo ""
        echo "WARNING: this branch is $BEHIND_UPSTREAM commit(s) BEHIND its own upstream."
        echo "Someone else pushed to it. Pull before pushing, or the push is rejected."
    fi
else
    echo "(no upstream — first push will need 'git push -u origin $CURRENT_BRANCH')"
fi
echo ""

echo "=== BEHIND $DEFAULT_BRANCH? ==="
BEHIND_DEFAULT=$(git rev-list --count "HEAD..origin/$DEFAULT_BRANCH" 2>/dev/null || echo "0")
if [[ "$BEHIND_DEFAULT" -gt 0 ]]; then
    echo "Behind origin/$DEFAULT_BRANCH by $BEHIND_DEFAULT commit(s)."
    echo "Not blocking — but if CI needs an up-to-date branch, run git-sync first."
else
    echo "Up to date with origin/$DEFAULT_BRANCH"
fi
echo ""

echo "=== OPEN PR ==="
if command -v gh >/dev/null 2>&1; then
    PR=$(gh pr view "$CURRENT_BRANCH" --json number,state,url,isDraft \
        --jq '[.number, .state, .url, (.isDraft|tostring)] | @tsv' 2>/dev/null || echo "")
    if [[ -n "$PR" ]]; then
        IFS=$'\t' read -r P_NUM P_STATE P_URL P_DRAFT <<< "$PR"
        echo "PR #$P_NUM ($P_STATE, draft=$P_DRAFT)"
        echo "$P_URL"
        echo ""
        echo "--- CI checks on the current head ---"
        gh pr checks "$P_NUM" 2>/dev/null || echo "(no checks reported yet)"
    else
        echo "(no PR for this branch — push will just update the remote branch)"
    fi
else
    echo "WARNING: gh CLI not found — cannot report PR or CI status"
fi
echo ""

# --- Repo-local pre-push checks ---------------------------------------------
# Invariants this repo declares for itself (spec drift, stale generated artifacts).
# Relevance is judged against everything the PR will contain after this push — the
# three-dot diff plus the uncommitted work about to be committed — not just the
# files in this one commit, because drift introduced earlier on the branch is still
# drift the push is about to publish.
CHANGED_FILES=$(mktemp)
repo_check_changed_files "$DEFAULT_BRANCH" > "$CHANGED_FILES"
emit_repo_checks_section "$CHANGED_FILES" "git-push-branch" "$DEFAULT_BRANCH" || true
rm -f "$CHANGED_FILES"
echo ""

echo "=== RECENT COMMITS (for style reference) ==="
git log --oneline -5 2>/dev/null || echo "(no commits yet)"
echo ""

if [[ -z "$(git status --porcelain)" && "$UNPUSHED_COUNT" -eq 0 ]]; then
    echo "=== NOTHING TO DO ==="
    echo "Working tree is clean and there are no unpushed commits."
    exit 3
fi
