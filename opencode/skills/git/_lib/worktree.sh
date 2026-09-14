#!/bin/bash
# Shared worktree helpers for the git-* skills.
#
# Why this exists: a repo can have more than one checkout (git worktrees, as used by
# Orca ADE). Git refuses to check out a branch that is already checked out somewhere
# else, so any script that does `git checkout <default>` dies with
#   fatal: 'main' is already used by worktree at '/path/to/other'
# the moment it runs from a linked worktree.
#
# The fix these helpers enable: never check out the default branch. Integrate against
# `origin/<default>` instead, and update the local default branch by ref only.
#
# Source with:
#   source "$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../../_lib/worktree.sh"
#
# The `cd -P` matters. These skills are reached through a symlink at the *skill
# directory* level (the catalog points to the source skill directory), so a
# plain `dirname`-relative `../..` would climb out into ~/.config/opencode/skills and miss
# _lib entirely. `cd -P` resolves to the real resource path first.

# True when the current checkout is a linked worktree rather than the main one.
is_linked_worktree() {
    local git_dir common_dir
    git_dir=$(git rev-parse --absolute-git-dir 2>/dev/null) || return 1
    common_dir=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null) || return 1
    [[ "$git_dir" != "$common_dir" ]]
}

# Echo the path of the worktree holding <branch>, or nothing if no worktree has it.
# Skips the current worktree — we only care about branches held *elsewhere*, since
# those are the ones we cannot check out.
branch_checked_out_elsewhere() {
    local branch="$1"
    local here
    here=$(git rev-parse --show-toplevel 2>/dev/null)

    git worktree list --porcelain 2>/dev/null | awk -v want="refs/heads/$branch" -v here="$here" '
        /^worktree /  { path = substr($0, 10) }
        /^branch /    { if (substr($0, 8) == want && path != here) { print path; exit } }
    '
}

# Fast-forward the local <default> branch from origin WITHOUT checking it out.
#
# `git fetch origin <branch>:<branch>` moves the local ref directly. It is refused by
# git when that branch is checked out anywhere (including here), so callers skip it in
# that case — harmless, because nothing downstream reads the local default branch: the
# integration target is always `origin/<default>`.
#
# Returns 0 when the ref was advanced or was already current, 1 when it was skipped,
# and 2 when the fast-forward was rejected because the local branch has diverged.
fast_forward_default_ref() {
    local default="$1"
    local current
    current=$(git branch --show-current 2>/dev/null)

    if [[ "$current" == "$default" ]]; then
        echo "Local '$default' is the current branch here — leaving it to the caller."
        return 1
    fi

    local holder
    holder=$(branch_checked_out_elsewhere "$default")
    if [[ -n "$holder" ]]; then
        echo "Local '$default' is checked out at $holder — not touching it."
        echo "Integration will use origin/$default, so this does not matter."
        return 1
    fi

    if ! git show-ref --verify --quiet "refs/heads/$default"; then
        echo "No local '$default' — creating it from origin/$default (no checkout)."
        git branch "$default" "origin/$default"
        return 0
    fi

    if git fetch origin "$default:$default" 2>/dev/null; then
        echo "Local '$default' fast-forwarded to origin/$default."
        return 0
    fi

    echo "Local '$default' could not be fast-forwarded — it has diverged from origin/$default."
    return 2
}
