#!/bin/bash
# Analyze a feature branch that already has commits, in preparation for opening a PR.
# Outputs: branch info, uncommitted work, the PR diff (three-dot), up-to-date check,
#          existing-PR check, PR template, the local checks that mirror CI, and the
#          repo's own declared pre-PR checks (see ../../_lib/repo-checks.sh).
#
# Usage: analyze-branch.sh
# Exit:  0  ready to PR
#        1  error (not a repo)
#        2  on the default branch — wrong skill
#        3  no commits to PR, and nothing uncommitted either — genuinely empty
#        4  blockers found (uncommitted work and/or branch behind default) — see BLOCKERS
#        5  no commits yet, but uncommitted work is present — commit it first, then PR.
#           This is the state a fresh Orca ADE worktree starts in: the branch already
#           exists with zero commits and the work is sitting in the working tree. It is
#           not an error, and git-branch-and-pr cannot take it either (that skill requires
#           the default branch), so this skill handles it.

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
    echo "This skill opens a PR for a feature branch that already has commits."
    echo "Use git-branch-and-pr to wrap default-branch changes into a new branch instead."
    exit 2
fi

echo "=== FETCHING ORIGIN ==="
git fetch origin --quiet 2>&1 || echo "WARNING: git fetch failed"
echo "(done)"
echo ""

BLOCKERS=()

# --- Uncommitted work -------------------------------------------------------
echo "=== UNCOMMITTED CHANGES ==="
PORCELAIN=$(git status --porcelain)
if [[ -n "$PORCELAIN" ]]; then
    echo "$PORCELAIN"
    echo ""
    echo "BLOCKER: this work is not committed and will NOT be in the PR."
    BLOCKERS+=("uncommitted-changes")
else
    echo "(clean — everything is committed)"
fi
echo ""

# --- Commits the PR will contain --------------------------------------------
echo "=== COMMITS ON THIS BRANCH (origin/$DEFAULT_BRANCH..HEAD) ==="
COMMITS=$(git log --oneline "origin/$DEFAULT_BRANCH..HEAD" 2>/dev/null || echo "")
if [[ -z "$COMMITS" ]]; then
    echo "(none)"
    echo ""
    if [[ -n "$PORCELAIN" ]]; then
        echo "NO COMMITS YET — but there is uncommitted work above."
        echo "Commit it first, then this branch is PR-able. See exit 5 in the header."
        exit 5
    fi
    echo "ERROR: nothing to PR — this branch has no commits beyond origin/$DEFAULT_BRANCH,"
    echo "and the working tree is clean. There is no work here."
    exit 3
fi
echo "$COMMITS"
COMMIT_COUNT=$(echo "$COMMITS" | wc -l | tr -d ' ')
echo ""
echo "($COMMIT_COUNT commit(s))"
echo ""

# --- Up to date with the default branch -------------------------------------
# Three-dot diffs and most CI guards assume the branch contains the tip of the
# default branch. If merge-base != origin/default, the branch is behind.
echo "=== UP TO DATE WITH origin/$DEFAULT_BRANCH? ==="
MERGE_BASE=$(git merge-base HEAD "origin/$DEFAULT_BRANCH" 2>/dev/null || echo "")
REMOTE_DEFAULT=$(git rev-parse "origin/$DEFAULT_BRANCH" 2>/dev/null || echo "")
if [[ -n "$MERGE_BASE" && -n "$REMOTE_DEFAULT" && "$MERGE_BASE" == "$REMOTE_DEFAULT" ]]; then
    echo "Yes — branch contains the tip of origin/$DEFAULT_BRANCH"
else
    BEHIND=$(git rev-list --count "HEAD..origin/$DEFAULT_BRANCH" 2>/dev/null || echo "?")
    echo "No — branch is behind origin/$DEFAULT_BRANCH by $BEHIND commit(s)."
    echo ""
    echo "BLOCKER: sync first (git-sync), then re-run."
    BLOCKERS+=("behind-default-branch")
fi
echo ""

# --- The PR diff ------------------------------------------------------------
# Three-dot (origin/default...HEAD) is what GitHub actually shows in the PR:
# the diff against the merge-base, not against the moving tip.
echo "=== PR DIFF STAT (origin/$DEFAULT_BRANCH...HEAD) ==="
git diff "origin/$DEFAULT_BRANCH...HEAD" --stat 2>/dev/null || echo "(unavailable)"
echo ""

DIFF_LINES=$(git diff "origin/$DEFAULT_BRANCH...HEAD" 2>/dev/null | wc -l | tr -d ' ')
echo "=== PR DIFF (origin/$DEFAULT_BRANCH...HEAD) ==="
if [[ "$DIFF_LINES" -gt 2000 ]]; then
    echo "(diff is $DIFF_LINES lines — too large to inline)"
    echo "Read it selectively per file:"
    echo "  git diff origin/$DEFAULT_BRANCH...HEAD -- <path>"
    echo ""
    echo "--- files changed ---"
    git diff "origin/$DEFAULT_BRANCH...HEAD" --name-status 2>/dev/null || true
else
    git diff "origin/$DEFAULT_BRANCH...HEAD" 2>/dev/null || true
fi
echo ""

# --- Existing PR ------------------------------------------------------------
echo "=== EXISTING PR CHECK ==="
if command -v gh >/dev/null 2>&1; then
    EXISTING=$(gh pr view "$CURRENT_BRANCH" --json number,state,url \
        --jq '[.number, .state, .url] | @tsv' 2>/dev/null || echo "")
    if [[ -n "$EXISTING" ]]; then
        IFS=$'\t' read -r E_NUM E_STATE E_URL <<< "$EXISTING"
        echo "A PR already exists: #$E_NUM ($E_STATE) $E_URL"
        echo "Do NOT create a duplicate. Report it, and offer to update the body instead."
    else
        echo "(no PR yet for this branch)"
    fi
else
    echo "WARNING: gh CLI not found — cannot check for an existing PR or open one"
fi
echo ""

# --- Upstream ---------------------------------------------------------------
echo "=== BRANCH UPSTREAM ==="
UPSTREAM=$(git rev-parse --abbrev-ref --symbolic-full-name @{u} 2>/dev/null || echo "")
if [[ -n "$UPSTREAM" ]]; then
    UNPUSHED=$(git rev-list --count @{u}..HEAD 2>/dev/null || echo "0")
    echo "Upstream: $UPSTREAM ($UNPUSHED unpushed commit(s))"
else
    echo "(no upstream — will need 'git push -u origin $CURRENT_BRANCH')"
fi
echo ""

# --- Local checks that mirror CI --------------------------------------------
# Read these and run the equivalent locally before opening the PR.
echo "=== CI WORKFLOWS (run the equivalent locally before opening the PR) ==="
if [[ -d ".github/workflows" ]]; then
    for wf in .github/workflows/*.yml .github/workflows/*.yaml; do
        [[ -f "$wf" ]] || continue
        if grep -q "pull_request" "$wf" 2>/dev/null; then
            echo "  $wf  (triggers on pull_request)"
        else
            echo "  $wf"
        fi
    done
else
    echo "(no .github/workflows)"
fi
echo ""

echo "=== LOCAL CHECK COMMANDS AVAILABLE ==="
if [[ -f "package.json" ]]; then
    echo "--- package.json scripts ---"
    grep -A 30 '"scripts"' package.json 2>/dev/null | grep -E '^\s+"' | head -20 || true
fi
if [[ -f "Makefile" ]]; then
    echo "--- Makefile targets ---"
    grep -E '^[a-zA-Z0-9_.-]+:' Makefile 2>/dev/null | cut -d: -f1 | head -20 || true
fi
if [[ -f "justfile" || -f "Justfile" ]]; then
    echo "--- just recipes ---"
    just --list 2>/dev/null | head -20 || true
fi
if [[ ! -f "package.json" && ! -f "Makefile" && ! -f "justfile" && ! -f "Justfile" ]]; then
    echo "(no package.json / Makefile / justfile found)"
fi
echo ""

# --- Repo-local pre-PR checks -----------------------------------------------
# Invariants this repo declares for itself (spec drift, stale generated artifacts)
# that no generic lint/build/test command knows about. Discovery only — the checks
# marked REQUIRED are run in Phase 3 via repo-check.sh, which applies each one's
# fail-on regex so the pass/fail call is deterministic.
CHANGED_FILES=$(mktemp)
repo_check_changed_files "$DEFAULT_BRANCH" > "$CHANGED_FILES"
emit_repo_checks_section "$CHANGED_FILES" "git-pr" "$DEFAULT_BRANCH" || true
rm -f "$CHANGED_FILES"
echo ""

# --- PR template ------------------------------------------------------------
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
echo ""

echo "=== RECENT COMMITS (for style reference) ==="
git log --oneline -5 2>/dev/null || echo "(no commits yet)"
echo ""

# --- Verdict ----------------------------------------------------------------
echo "=== BLOCKERS ==="
if [[ ${#BLOCKERS[@]} -eq 0 ]]; then
    echo "(none — ready to open the PR once local checks pass)"
    exit 0
fi
for b in "${BLOCKERS[@]}"; do
    echo "  - $b"
done
exit 4
