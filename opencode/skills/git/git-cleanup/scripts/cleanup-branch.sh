#!/bin/bash
# Refresh the default branch, then delete the merged feature branch (local + remote).
#
# REQUIRES --merge-verified as the third argument. Pass it ONLY after
# verify-merged.sh exited 0. The force-delete fallback below is licensed by that
# check and by nothing else.
#
# Usage: cleanup-branch.sh <branch> <default_branch> --merge-verified
# Exit:  0   done
#        1   usage / error
#        10  default branch could not fast-forward (diverged) — caller must resolve

set -e

BRANCH="$1"
DEFAULT_BRANCH="$2"
VERIFIED="$3"

if [[ -z "$BRANCH" || -z "$DEFAULT_BRANCH" ]]; then
    echo "Usage: $0 <branch> <default_branch> --merge-verified"
    exit 1
fi

if [[ "$VERIFIED" != "--merge-verified" ]]; then
    echo "ERROR: refusing to run without --merge-verified."
    echo "Run verify-merged.sh first and confirm it exited 0 (PR state MERGED)."
    exit 1
fi

if [[ "$BRANCH" == "$DEFAULT_BRANCH" ]]; then
    echo "ERROR: refusing to delete the default branch ($DEFAULT_BRANCH)"
    exit 1
fi

source "$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../../_lib/worktree.sh"

echo "=== Fetching origin (with --prune) ==="
# --prune drops the remote-tracking ref if GitHub auto-deleted the head branch on merge
git fetch origin --prune

# A linked worktree (Orca ADE) cannot switch to the default branch — it is checked out
# in the main checkout, and git refuses a second checkout of the same branch. It also
# cannot delete $BRANCH, because that is the branch this worktree is standing on.
# So in a worktree, cleanup is: refresh the default ref, drop the remote branch, and
# hand the local branch + directory to `orca worktree rm`, which removes both.
LINKED=no
if is_linked_worktree; then
    LINKED=yes
fi

if [[ "$LINKED" == "yes" ]]; then
    echo ""
    echo "=== Linked worktree — not switching branches ==="
    echo "This checkout is a linked worktree at $(git rev-parse --show-toplevel)."
    set +e
    fast_forward_default_ref "$DEFAULT_BRANCH"
    FF_STATUS=$?
    set -e
    if [[ $FF_STATUS -eq 2 ]]; then
        echo ""
        echo "ERROR: local $DEFAULT_BRANCH has diverged from origin/$DEFAULT_BRANCH."
        echo "Resolve that in the main checkout first. Branch '$BRANCH' has NOT been deleted."
        exit 10
    fi
else
    echo ""
    echo "=== Switching to $DEFAULT_BRANCH ==="
    if git show-ref --verify --quiet "refs/heads/$DEFAULT_BRANCH"; then
        git switch "$DEFAULT_BRANCH"
    else
        echo "No local $DEFAULT_BRANCH — creating it from origin/$DEFAULT_BRANCH"
        git switch -c "$DEFAULT_BRANCH" "origin/$DEFAULT_BRANCH"
    fi

    echo ""
    echo "=== Pulling latest origin/$DEFAULT_BRANCH (fast-forward only) ==="
    # --ff-only is deliberate: local default should only ever fast-forward.
    # A plain pull could invent a surprise merge commit on the default branch.
    if ! git pull --ff-only origin "$DEFAULT_BRANCH"; then
        echo ""
        echo "ERROR: fast-forward failed. Local $DEFAULT_BRANCH has diverged from origin/$DEFAULT_BRANCH."
        echo "Something was committed directly to local $DEFAULT_BRANCH."
        echo "Do NOT force this. Resolve it with the user (see git-sync's"
        echo "conflict procedure), then re-run this script."
        echo ""
        echo "Branch '$BRANCH' has NOT been deleted."
        exit 10
    fi
fi

echo ""
echo "=== Remote branch ==="
if git ls-remote --exit-code --heads origin "$BRANCH" >/dev/null 2>&1; then
    git push origin --delete "$BRANCH"
    echo "remote branch deleted"
else
    echo "remote branch already gone (auto-deleted on merge)"
fi

echo ""
if [[ "$LINKED" == "yes" ]]; then
    echo "=== Local branch $BRANCH — left for Orca ==="
    echo "Still checked out by this worktree, so git cannot delete it from here."
    echo "Remove the worktree and the branch together with:"
    echo ""
    echo "    orca worktree rm --worktree active"
    echo ""
    echo "(or pass the full selector from 'orca worktree list --json' if you are not"
    echo " running this from inside the worktree)."
    echo ""
    echo "=== DONE (remote cleaned; local worktree awaiting removal) ==="
    exit 0
fi

echo "=== Deleting local branch $BRANCH ==="
if git branch -d "$BRANCH" 2>/dev/null; then
    echo "deleted (fast-forward-merged, safe delete)"
else
    # -d refuses after a squash or rebase merge ("not fully merged") because the
    # branch commits are not ancestors of the default branch. gh already confirmed
    # state == MERGED, so the work IS upstream. Force-delete is safe HERE ONLY.
    git branch -D "$BRANCH"
    echo "deleted (squash/rebase merge — forced, licensed by the verified MERGED state)"
fi

echo ""
echo "=== DONE ==="
echo "Now on: $(git branch --show-current)"
git log --oneline -1
