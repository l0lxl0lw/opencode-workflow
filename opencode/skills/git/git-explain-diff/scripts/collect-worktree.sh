#!/bin/bash
# Collect everything needed to explain the uncommitted working tree, in one call.
#
# Emits three populations -- staged, unstaged, and UNTRACKED. The third is the
# reason this script exists: `git diff` cannot see a new file, and a new file is
# usually the point of the change.
#
# Usage: collect-worktree.sh [--max-lines N] [--max-bytes N]
#   --max-lines  per-file diff size above which a file is counted, not read (default 800)
#   --max-bytes  per-untracked-file size above which contents are not printed (default 60000)

set -uo pipefail

MAX_LINES=800
MAX_BYTES=60000

while [[ $# -gt 0 ]]; do
    case "$1" in
        --max-lines) MAX_LINES="$2"; shift 2 ;;
        --max-bytes) MAX_BYTES="$2"; shift 2 ;;
        -h|--help)   sed -n '2,12p' "$0"; exit 0 ;;
        *) echo "ERROR: unknown argument '$1'" >&2; exit 2 ;;
    esac
done

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "ERROR: not in a git repository" >&2
    exit 1
fi

cd "$(git rev-parse --show-toplevel)" || exit 1

# Read-only throughout: -c sets quotepath for these invocations only, never
# touching the user's repo config.
GIT() { git -c core.quotepath=false "$@"; }

HAS_HEAD=1
git rev-parse --verify -q HEAD >/dev/null || HAS_HEAD=0

# --- paths that are counted but not read -------------------------------------
# Every entry is reported under SCOPE NOTES and excluded from the printed diffs
# via a negative pathspec, so a truncation is never silent.
#   SKIPPED       one display line per file: "<path><TAB><reason>"
#   SKIPPED_PATHS every path to exclude -- BOTH sides of a rename, otherwise the
#                 old name survives the exclusion and prints as a bare deletion,
#                 which reads as "you deleted this file"
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

# classify <added> <deleted> <path> -> prints a reason, or nothing if readable
classify() {
    local added="$1" deleted="$2" path="$3"
    if [[ "$added" == "-" || "$deleted" == "-" ]]; then
        echo "binary"; return
    fi
    if is_lockfile "$path"; then echo "lockfile"; return; fi
    if is_generated "$path"; then echo "generated"; return; fi
    if (( added + deleted > MAX_LINES )); then
        echo "oversized (${added}+/${deleted}- > $MAX_LINES lines)"; return
    fi
}

# numstat <git-diff-args...> -> "added<TAB>deleted<TAB>newpath<TAB>oldpath"
# (oldpath empty unless this is a rename/copy). Parses the -z form, so paths with
# spaces survive intact.
numstat() {
    local rec added rest deleted path old
    GIT diff --numstat -z -M -C "$@" | while IFS= read -r -d '' rec; do
        added="${rec%%$'\t'*}"
        rest="${rec#*$'\t'}"
        deleted="${rest%%$'\t'*}"
        path="${rest#*$'\t'}"
        old=""
        if [[ -z "$path" ]]; then          # rename/copy: old and new follow as fields
            IFS= read -r -d '' old  || break
            IFS= read -r -d '' path || break
        fi
        printf '%s\t%s\t%s\t%s\n' "$added" "$deleted" "$path" "$old"
    done
}

collect_skips() {
    local added deleted path old reason
    while IFS=$'\t' read -r added deleted path old; do
        [[ -n "$path" ]] || continue
        reason="$(classify "$added" "$deleted" "$path")"
        [[ -n "$reason" ]] || continue
        if [[ -n "$old" ]]; then
            SKIPPED+=("$old => $path"$'\t'"$reason")
            SKIPPED_PATHS+=("$old" "$path")
        else
            SKIPPED+=("$path"$'\t'"$reason")
            SKIPPED_PATHS+=("$path")
        fi
    done < <( { numstat --cached; numstat; } | sort -u -t$'\t' -k3 )
}

# Negative pathspecs, so rename detection still works on what remains (a positive
# pathspec listing only the survivors would break it).
diff_excluding() {   # diff_excluding <git-diff-args...>
    local p
    EX=()
    for p in "${SKIPPED_PATHS[@]+"${SKIPPED_PATHS[@]}"}"; do
        EX+=(":(exclude,literal)$p")
    done
    GIT diff -M -C "$@" -- "${EX[@]+"${EX[@]}"}"
}

collect_skips

# =============================================================================
echo "=== BRANCH ==="
BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "(no commits yet)")"
echo "branch:   $BRANCH"
UPSTREAM="$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || true)"
if [[ -n "$UPSTREAM" ]]; then
    read -r BEHIND AHEAD < <(git rev-list --left-right --count "$UPSTREAM...HEAD" 2>/dev/null || echo "0 0")
    echo "upstream: $UPSTREAM (ahead $AHEAD, behind $BEHIND)"
else
    echo "upstream: none -- this branch has never been pushed"
fi
if (( HAS_HEAD )); then
    echo "HEAD:     $(git log -1 --format='%h %s' 2>/dev/null)"
else
    echo "HEAD:     none -- repository has no commits; every tracked file is new"
fi
echo ""

echo "=== STATUS (porcelain v2, all untracked) ==="
GIT status --porcelain=v2 --untracked-files=all --branch
echo ""

echo "=== STAT: STAGED ==="
if (( HAS_HEAD )); then GIT diff --cached --stat -M -C; else echo "(no HEAD; nothing can be staged against it)"; fi
echo ""

echo "=== STAT: UNSTAGED ==="
GIT diff --stat -M -C
echo ""

# Distinguish "nothing changed" from "everything that changed was skipped" --
# conflating them is exactly the silent truncation this script exists to avoid.
report_diff() {   # report_diff <label> <raw-stat> <body>
    local label="$1" raw="$2" body="$3"
    if [[ -n "$body" ]]; then
        echo "$body"
    elif [[ -n "$raw" ]]; then
        echo "(files ARE $label, but every one was counted, not read -- see SCOPE NOTES below."
        echo " Do not report this as nothing. Read the named files directly first.)"
    else
        echo "(nothing $label)"
    fi
}

echo "=== DIFF: STAGED ==="
if (( HAS_HEAD )); then
    report_diff "staged" "$(GIT diff --cached --name-only -M -C)" "$(diff_excluding --cached)"
else
    echo "(no HEAD)"
fi
echo ""

echo "=== DIFF: UNSTAGED ==="
report_diff "unstaged" "$(GIT diff --name-only -M -C)" "$(diff_excluding)"
echo ""

# -----------------------------------------------------------------------------
# Untracked files. Invisible to every `git diff` above -- this section is the
# only place they appear.
echo "=== UNTRACKED FILES ==="
UNTRACKED=()
while IFS= read -r -d '' f; do UNTRACKED+=("$f"); done \
    < <(GIT ls-files --others --exclude-standard -z)

if (( ${#UNTRACKED[@]} == 0 )); then
    echo "(none)"
else
    echo "${#UNTRACKED[@]} untracked file(s):"
    printf '  %s\n' "${UNTRACKED[@]}"
    echo ""
    for f in "${UNTRACKED[@]}"; do
        size=$(wc -c < "$f" 2>/dev/null | tr -d ' ')
        size=${size:-0}
        reason=""
        if is_lockfile "$f";  then reason="lockfile"
        elif is_generated "$f"; then reason="generated"
        elif [[ -s "$f" ]] && ! LC_ALL=C grep -Iq . -- "$f" 2>/dev/null; then reason="binary"
        elif (( size > MAX_BYTES )); then reason="oversized (${size}B > ${MAX_BYTES}B)"
        fi

        if [[ -n "$reason" ]]; then
            echo "--- $f (${size}B) -- COUNTED, NOT READ: $reason"
            SKIPPED+=("$f"$'\t'"untracked, $reason")
        else
            echo "--- $f (${size}B, $(wc -l < "$f" 2>/dev/null | tr -d ' ') lines) ---"
            cat -- "$f"
            echo "--- end $f ---"
        fi
        echo ""
    done
fi
echo ""

# -----------------------------------------------------------------------------
echo "=== LOCALLY HIDDEN FILES ==="
# assume-unchanged (lowercase tag) and skip-worktree (S) edits never appear in
# any diff, on purpose. If one is set, a real modification can be sitting in the
# tree completely unreported.
HIDDEN="$(GIT ls-files -v | awk '$1 ~ /^[a-z]$/ || $1 == "S" {print}')"
if [[ -n "$HIDDEN" ]]; then
    echo "WARNING: these paths are assume-unchanged/skip-worktree; edits to them are invisible to git diff:"
    echo "$HIDDEN"
else
    echo "(none -- no assume-unchanged or skip-worktree paths)"
fi
echo ""

echo "=== SUBMODULES ==="
if [[ -f .gitmodules ]]; then
    GIT submodule status 2>/dev/null || echo "(git submodule status failed)"
    echo "NOTE: a submodule shows as a one-line pointer change; the work is in the other repo."
else
    echo "(none)"
fi
echo ""

echo "=== SCOPE NOTES: COUNTED, NOT READ ==="
if (( ${#SKIPPED[@]} == 0 )); then
    echo "(none -- every changed file above was read in full)"
else
    echo "These files changed but their contents were NOT included above."
    echo "Name them in the ## Scope section; never let a truncation pass as full coverage."
    printf '%s\n' "${SKIPPED[@]}" | sort -u | awk -F'\t' '{printf "  %-55s %s\n", $1, $2}'
fi
echo ""

echo "=== RECENT COMMITS (style + context) ==="
if (( HAS_HEAD )); then git log --oneline -8; else echo "(no commits)"; fi
