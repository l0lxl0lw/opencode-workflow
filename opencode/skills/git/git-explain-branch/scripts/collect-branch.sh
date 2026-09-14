#!/bin/bash
# Collect everything needed to explain this branch against the default branch.
#
# THE RULE THIS SCRIPT ENFORCES: three dots for `diff`, two dots for `log`.
#   git diff main...HEAD  == git diff $(git merge-base main HEAD) HEAD  -- your work only
#   git diff main..HEAD   ==  your work MINUS main's work, so main's commits show up
#                             as your deletions and the explanation comes out backwards
#   git log  main..HEAD   -- your commits only          (correct)
#   git log  main...HEAD  -- symmetric difference       (wrong: includes main's commits)
#
# Usage: collect-branch.sh [--no-fetch] [--base <ref>] [--max-lines N]
#   --no-fetch   skip `git fetch` (offline, or you already fetched)
#   --base       compare against this ref instead of the detected default branch
#   --max-lines  per-file diff size above which a file is counted, not read (default 800)

set -uo pipefail

DO_FETCH=1
BASE_REF=""
MAX_LINES=800

while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-fetch)  DO_FETCH=0; shift ;;
        --base)      BASE_REF="$2"; shift 2 ;;
        --max-lines) MAX_LINES="$2"; shift 2 ;;
        -h|--help)   sed -n '2,18p' "$0"; exit 0 ;;
        *) echo "ERROR: unknown argument '$1'" >&2; exit 2 ;;
    esac
done

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "ERROR: not in a git repository" >&2
    exit 1
fi
cd "$(git rev-parse --show-toplevel)" || exit 1

GIT() { git -c core.quotepath=false "$@"; }

BRANCH="$(git rev-parse --abbrev-ref HEAD)"

# --- fetch --------------------------------------------------------------------
# The one non-read-only step in this skill: it moves remote-tracking refs (never
# your branch, never the working tree). Without it, "what main gained" is answered
# from whenever you last fetched, which is the quiet way to miss a collision.
echo "=== FETCH ==="
if (( DO_FETCH )); then
    if git remote get-url origin >/dev/null 2>&1; then
        if GIT fetch --quiet origin 2>&1; then
            echo "fetched origin (remote-tracking refs updated; branch and worktree untouched)"
        else
            echo "WARNING: fetch failed -- origin may be stale. 'Collisions with main' below"
            echo "         is only as fresh as your last successful fetch."
        fi
    else
        echo "no 'origin' remote -- comparing against local refs only"
    fi
else
    echo "SKIPPED (--no-fetch). origin refs are as stale as your last fetch; say so in ## Scope."
fi
echo ""

# --- resolve the default branch ----------------------------------------------
echo "=== BASE RESOLUTION ==="
if [[ -z "$BASE_REF" ]]; then
    if BASE_REF="$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null)"; then
        echo "default branch: $BASE_REF (from refs/remotes/origin/HEAD)"
    elif git rev-parse --verify -q origin/main >/dev/null; then
        BASE_REF="origin/main"; echo "default branch: origin/main (origin/HEAD unset; guessed)"
    elif git rev-parse --verify -q origin/master >/dev/null; then
        BASE_REF="origin/master"; echo "default branch: origin/master (origin/HEAD unset; guessed)"
    elif command -v gh >/dev/null 2>&1 && \
         D="$(gh repo view --json defaultBranchRef -q .defaultBranchRef.name 2>/dev/null)" && [[ -n "$D" ]]; then
        BASE_REF="origin/$D"; echo "default branch: origin/$D (from gh)"
    elif git rev-parse --verify -q main >/dev/null; then
        BASE_REF="main"; echo "default branch: main (local; no remote)"
    elif git rev-parse --verify -q master >/dev/null; then
        BASE_REF="master"; echo "default branch: master (local; no remote)"
    else
        echo "ERROR: could not resolve a default branch. Pass --base <ref>." >&2
        exit 1
    fi
else
    echo "default branch: $BASE_REF (given with --base)"
fi

if ! git rev-parse --verify -q "$BASE_REF" >/dev/null; then
    echo "ERROR: '$BASE_REF' is not a valid ref" >&2
    exit 1
fi

MERGE_BASE="$(git merge-base "$BASE_REF" HEAD)" || {
    echo "ERROR: no common ancestor between $BASE_REF and HEAD -- unrelated histories" >&2
    exit 1
}
echo "branch:         $BRANCH"
echo "merge-base:     $(git log -1 --format='%h %ad %s' --date=short "$MERGE_BASE")"
echo "branch tip:     $(git log -1 --format='%h %ad %s' --date=short HEAD)"

if [[ "$(git rev-parse HEAD)" == "$MERGE_BASE" ]]; then
    echo ""
    echo "NOTE: HEAD *is* the merge-base -- this branch has no commits of its own."
    echo "      Any work here is uncommitted; explain it with git-explain-diff instead."
fi
echo ""

# --- what is NOT in this scope ------------------------------------------------
echo "=== EXCLUDED FROM THIS SCOPE ==="
DIRTY="$(GIT status --porcelain=v2 --untracked-files=all)"
if [[ -n "$DIRTY" ]]; then
    echo "UNCOMMITTED WORK -- present in your tree, absent from every diff below."
    echo "State this in ## Scope. To explain it, use git-explain-diff."
    GIT status --short --untracked-files=all
else
    echo "(working tree clean -- the diff below is the whole story)"
fi
MERGES="$(git rev-list --count --merges "$MERGE_BASE..HEAD")"
(( MERGES > 0 )) && echo "" && echo "$MERGES merge commit(s) on this branch are omitted from the log below (--no-merges);" \
    && echo "the three-dot diff already excludes whatever they brought in from $BASE_REF."
echo ""

# --- commits ------------------------------------------------------------------
echo "=== COMMITS (log: TWO dots) ==="
COMMIT_COUNT="$(git rev-list --count --no-merges "$MERGE_BASE..HEAD")"
echo "$COMMIT_COUNT non-merge commit(s) on $BRANCH since the merge-base:"
GIT log --oneline --no-merges "$MERGE_BASE..HEAD"
echo ""
echo "--- with bodies ---"
GIT log --no-merges --format='%h %an %ad%n%B%n---' --date=short "$MERGE_BASE..HEAD"
echo ""
echo "NOTE: commit messages are evidence, not truth. A message can describe an approach"
echo "      abandoned three commits later. Verify every claim against the diff below."
echo ""

# --- work that nets to zero ---------------------------------------------------
echo "=== TOUCHED BUT NET-ZERO ==="
# Files the commits touched that the final diff does not show: written then
# reverted, or churned back to their original contents. Invisible in any diff.
LOG_FILES="$(GIT log --no-merges --name-only --pretty=format: "$MERGE_BASE..HEAD" | sed '/^$/d' | sort -u)"
DIFF_FILES="$(GIT diff --name-only -M -C "$BASE_REF...HEAD" | sort -u)"
NETZERO="$(comm -23 <(echo "$LOG_FILES") <(echo "$DIFF_FILES") 2>/dev/null)"
if [[ -n "$NETZERO" ]]; then
    echo "These files were edited by commits on this branch but do NOT appear in the final diff --"
    echo "the work was reverted or churned back. It is real history and zero net change:"
    echo "$NETZERO" | sed 's/^/  /'
    echo "(a rename also lands here under its old name -- check the diff before calling it a revert)"
else
    echo "(none -- every file the commits touched still differs from $BASE_REF)"
fi
echo ""

# --- classification -----------------------------------------------------------
# SKIPPED       one display line per file, reported under SCOPE NOTES
# SKIPPED_PATHS every path to exclude from the printed diff -- BOTH sides of a
#               rename, otherwise the old name survives the exclusion and prints
#               as a bare deletion, which reads as "you deleted this file"
SKIPPED=()
SKIPPED_PATHS=()

is_lockfile() {
    case "${1##*/}" in
        package-lock.json|yarn.lock|pnpm-lock.yaml|npm-shrinkwrap.json|bun.lockb|\
        Cargo.lock|go.sum|poetry.lock|uv.lock|Pipfile.lock|Gemfile.lock|composer.lock|\
        flake.lock|mix.lock|pubspec.lock|packages.lock.json|*.lock) return 0 ;;
    esac
    return 1
}
is_generated() {
    case "$1" in
        vendor/*|*/vendor/*|node_modules/*|*/node_modules/*|\
        dist/*|*/dist/*|build/*|*/build/*|target/*|*/target/*|\
        *.min.js|*.min.css|*.map|*.pb.go|*_pb2.py|*_pb2_grpc.py|*.pb.cc|*.pb.h|\
        *_generated.go|*.generated.*|*.g.dart|*.freezed.dart|*/__snapshots__/*) return 0 ;;
    esac
    return 1
}

OLDPATH=""
while IFS= read -r -d '' rec; do
    added="${rec%%$'\t'*}"; rest="${rec#*$'\t'}"
    deleted="${rest%%$'\t'*}"; path="${rest#*$'\t'}"
    OLDPATH=""
    if [[ -z "$path" ]]; then          # rename/copy: old and new follow as fields
        IFS= read -r -d '' OLDPATH || break
        IFS= read -r -d '' path    || break
    fi
    reason=""
    if [[ "$added" == "-" || "$deleted" == "-" ]]; then reason="binary"
    elif is_lockfile "$path";  then reason="lockfile"
    elif is_generated "$path"; then reason="generated"
    elif (( added + deleted > MAX_LINES )); then reason="oversized (${added}+/${deleted}- > $MAX_LINES lines)"
    fi
    if [[ -n "$reason" ]]; then
        if [[ -n "$OLDPATH" ]]; then
            SKIPPED+=("$OLDPATH => $path"$'\t'"$reason")
            SKIPPED_PATHS+=("$OLDPATH" "$path")
        else
            SKIPPED+=("$path"$'\t'"$reason")
            SKIPPED_PATHS+=("$path")
        fi
    fi
done < <(GIT diff --numstat -z -M -C "$BASE_REF...HEAD")

EXCLUDES=()
for p in "${SKIPPED_PATHS[@]+"${SKIPPED_PATHS[@]}"}"; do
    EXCLUDES+=(":(exclude,literal)$p")
done

# --- the diff -----------------------------------------------------------------
echo "=== STAT (diff: THREE dots) ==="
GIT diff --stat -M -C "$BASE_REF...HEAD"
echo ""

echo "=== DIFF (diff: THREE dots) ==="
OUT="$(GIT diff -M -C "$BASE_REF...HEAD" -- "${EXCLUDES[@]+"${EXCLUDES[@]}"}")"
if [[ -n "$OUT" ]]; then
    echo "$OUT"
elif (( ${#SKIPPED[@]} )); then
    # Distinguish "nothing changed" from "everything that changed was skipped" --
    # conflating them is exactly the silent truncation this script exists to avoid.
    echo "(EVERY changed file was counted, not read -- the whole change is in SCOPE NOTES below."
    echo " Do not report this branch as empty. Re-run with a higher --max-lines, or read the"
    echo " named files directly, before explaining anything.)"
else
    echo "(no changes vs $BASE_REF -- this branch's commits net to nothing)"
fi
echo ""

echo "=== SCOPE NOTES: COUNTED, NOT READ ==="
if (( ${#SKIPPED[@]} == 0 )); then
    echo "(none -- every changed file above was read in full)"
else
    echo "These files changed but their contents were NOT included above."
    echo "Name them in ## Scope; never let a truncation pass as full coverage."
    printf '%s\n' "${SKIPPED[@]}" | sort -u | awk -F'\t' '{printf "  %-55s %s\n", $1, $2}'
fi
echo ""

# --- collisions ---------------------------------------------------------------
echo "=== COLLISIONS WITH $BASE_REF ==="
# What the base branch gained since the merge-base, restricted to the files this
# branch also touched. Textual conflicts are the cheap half; the expensive half is
# the semantic one, where both sides merge clean and the behavior still breaks.
BASE_AHEAD="$(git rev-list --count "$MERGE_BASE..$BASE_REF")"
echo "$BASE_REF is $BASE_AHEAD commit(s) ahead of the merge-base."
if (( BASE_AHEAD == 0 )); then
    echo "(nothing landed on $BASE_REF since you branched -- no collisions possible)"
else
    if [[ -z "$DIFF_FILES" ]]; then
        echo "(this branch changes no files)"
    else
        PATHS=()   # not mapfile: macOS ships bash 3.2
        while IFS= read -r p; do [[ -n "$p" ]] && PATHS+=("$p"); done <<< "$DIFF_FILES"
        HITS="$(GIT log --oneline "$MERGE_BASE..$BASE_REF" -- "${PATHS[@]}")"
        if [[ -n "$HITS" ]]; then
            echo "Commits on $BASE_REF touching files this branch also changes:"
            echo "$HITS" | sed 's/^/  /'
            echo ""
            echo "Overlapping files:"
            GIT log --name-only --pretty=format: "$MERGE_BASE..$BASE_REF" -- "${PATHS[@]}" \
                | sed '/^$/d' | sort | uniq -c | sort -rn | sed 's/^/  /'
            echo ""
            echo "Check each for a SEMANTIC conflict, not just a textual one."
        else
            echo "(none -- no $BASE_REF commit touches a file this branch changes)"
        fi
    fi
fi
