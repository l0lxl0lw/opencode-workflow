#!/bin/bash
# Rebase the current feature branch onto the default branch, behind a safety branch.
#
# Tracks which commits conflicted across the whole rebase so the bail-out test is
# mechanical rather than a judgement call: a conflict confined to ONE commit is fine,
# but the moment a second commit conflicts you are re-resolving the same collision
# once per commit, against trees that never existed. A merge resolves it once.
#
# Usage: rebase-main.sh <default_branch>   start (creates safety branch)
#        rebase-main.sh --continue         stage resolutions and continue
#        rebase-main.sh --abort            abort, restoring the pre-rebase state
#        rebase-main.sh --status           report where the rebase is
#
# Exit:  0   rebase complete
#        1   error
#        10  conflicts — resolve them, then --continue
#        20  BAIL OUT: conflicts span more than one commit — abort and merge instead

set +e

GIT_DIR=$(git rev-parse --git-dir 2>/dev/null)
if [[ -z "$GIT_DIR" ]]; then
    echo "ERROR: Not in a git repository"
    exit 1
fi

TRACK_FILE="$GIT_DIR/.git-sync-conflicted-commits"

rebase_in_progress() {
    [[ -d "$GIT_DIR/rebase-merge" || -d "$GIT_DIR/rebase-apply" ]]
}

show_progress() {
    if [[ -f "$GIT_DIR/rebase-merge/msgnum" ]]; then
        echo "Progress: commit $(cat "$GIT_DIR/rebase-merge/msgnum") of $(cat "$GIT_DIR/rebase-merge/end")"
    elif [[ -f "$GIT_DIR/rebase-apply/next" ]]; then
        echo "Progress: commit $(cat "$GIT_DIR/rebase-apply/next") of $(cat "$GIT_DIR/rebase-apply/last")"
    fi
}

# Report conflict state and decide whether to keep going or bail out to a merge.
report_conflicts() {
    CONFLICTED=$(git diff --name-only --diff-filter=U)
    if [[ -z "$CONFLICTED" ]]; then
        return 1  # no conflicts
    fi

    REPLAYING=$(git rev-parse --short REBASE_HEAD 2>/dev/null || echo "unknown")
    REPLAYING_SUBJ=$(git log --oneline -1 REBASE_HEAD 2>/dev/null || echo "(unknown commit)")

    # Record this commit as having conflicted (deduped)
    touch "$TRACK_FILE"
    if ! grep -qx "$REPLAYING" "$TRACK_FILE" 2>/dev/null; then
        echo "$REPLAYING" >> "$TRACK_FILE"
    fi
    DISTINCT=$(sort -u "$TRACK_FILE" | grep -c . || echo 0)

    echo "=== CONFLICTS ==="
    show_progress
    echo "Replaying: $REPLAYING_SUBJ"
    echo ""
    echo "Conflicted files:"
    echo "$CONFLICTED"
    echo ""
    echo "Commits that have conflicted so far in this rebase: $DISTINCT"
    echo ""

    if [[ "$DISTINCT" -gt 1 ]]; then
        echo "=== BAIL OUT ==="
        echo "Conflicts have now hit $DISTINCT separate commits. Continuing means"
        echo "re-resolving the same collision once per commit, each time against a"
        echo "partial tree that never existed in the repo."
        echo ""
        echo "Abort and merge instead:"
        echo "  bash $0 --abort"
        echo "  bash \"$(dirname "$0")/merge-main.sh\" <default_branch>"
        return 20
    fi

    echo "Confined to one commit — safe to resolve and continue."
    echo "Resolve each conflict WITH the user, then: bash $0 --continue"
    return 10
}

case "$1" in
    --status)
        if ! rebase_in_progress; then
            echo "(no rebase in progress)"
            exit 0
        fi
        report_conflicts
        rc=$?
        [[ $rc -eq 1 ]] && { echo "Rebase in progress, no conflicts staged."; show_progress; exit 10; }
        exit $rc
        ;;

    --abort)
        if ! rebase_in_progress; then
            echo "ERROR: no rebase in progress"
            exit 1
        fi
        echo "=== Aborting rebase ==="
        git rebase --abort
        rm -f "$TRACK_FILE"
        echo "Pre-rebase state restored exactly. Nothing was changed."
        git log --oneline -1
        exit 0
        ;;

    --continue)
        if ! rebase_in_progress; then
            echo "ERROR: no rebase in progress"
            exit 1
        fi
        # Refuse to continue with markers still in the tree
        if ! bash "$(dirname "$0")/verify-resolution.sh" --quiet; then
            echo "ERROR: conflict markers are still present. Resolve them before continuing."
            bash "$(dirname "$0")/verify-resolution.sh"
            exit 1
        fi
        git add -A
        echo "=== Continuing rebase ==="
        git rebase --continue
        RC=$?
        if rebase_in_progress; then
            report_conflicts
            rc=$?
            [[ $rc -eq 1 ]] && { echo "Rebase paused without conflicts (exit $RC)."; show_progress; exit 10; }
            exit $rc
        fi
        rm -f "$TRACK_FILE"
        echo ""
        echo "=== REBASE COMPLETE ==="
        git log --oneline --graph -8
        exit 0
        ;;
esac

# ---- start a rebase --------------------------------------------------------

DEFAULT_BRANCH="$1"
if [[ -z "$DEFAULT_BRANCH" ]]; then
    echo "Usage: $0 <default_branch> | --continue | --abort | --status"
    exit 1
fi

if rebase_in_progress; then
    echo "ERROR: a rebase is already in progress. Use --continue, --abort or --status."
    exit 1
fi

CURRENT_BRANCH=$(git branch --show-current)
if [[ "$CURRENT_BRANCH" == "$DEFAULT_BRANCH" ]]; then
    echo "ERROR: on the default branch ($DEFAULT_BRANCH); refusing to rebase it onto itself"
    exit 1
fi

if [[ -n "$(git status --porcelain)" ]]; then
    echo "ERROR: working tree is dirty. Stash or commit before rebasing."
    git status --short
    exit 1
fi

rm -f "$TRACK_FILE"

# A rebase rewrites history: the old commits become unreachable the moment the
# branch ref moves. The safety branch is a free, instant undo.
SAFETY="backup/pre-rebase-$CURRENT_BRANCH-$(git rev-parse --short HEAD)"
echo "=== Creating safety branch ==="
git branch -f "$SAFETY"
echo "$SAFETY"
echo "Undo at any time with: git reset --hard $SAFETY"
echo ""

# Rebase onto the REMOTE ref, not the local branch. The local default branch may be
# checked out in another worktree (Orca ADE) and stale or absent here; origin/<default>
# is what sync-main.sh just fetched and is correct in every checkout layout.
UPSTREAM="origin/$DEFAULT_BRANCH"
if ! git rev-parse --verify --quiet "$UPSTREAM" >/dev/null; then
    echo "ERROR: $UPSTREAM does not exist. Fetch first."
    exit 1
fi

echo "=== Rebasing $CURRENT_BRANCH onto $UPSTREAM ==="
# No -X ours / -X theirs: they resolve silently and defeat the entire point.
git rebase "$UPSTREAM"

if rebase_in_progress; then
    report_conflicts
    rc=$?
    [[ $rc -eq 1 ]] && { echo "Rebase paused without conflicts."; show_progress; exit 10; }
    exit $rc
fi

rm -f "$TRACK_FILE"
echo ""
echo "=== REBASE COMPLETE (clean) ==="
echo "Safety branch left behind: $SAFETY"
git log --oneline --graph -8
exit 0
