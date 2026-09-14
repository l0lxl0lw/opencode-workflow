#!/bin/bash
# Repo-local pre-PR checks: discovery and deterministic gating, shared by the
# git-pr / git-push-branch / git-branch-and-pr skills.
#
# Why this exists: a repo often has consistency invariants that CI does not catch
# and that no generic lint/build/test command knows about — an OpenAPI spec that
# has drifted from the routes the code actually registers, a checked-in generated
# client that no longer matches its schema, a migration that no model reflects.
# The repo knows about these; the skill does not. This library lets the repo
# declare them, in the skill that already owns the fix.
#
# The contract: any skill under <repo>/.claude/skills/*/SKILL.md may add a
# `pre-pr:` block to its YAML frontmatter.
#
#   ---
#   name: ocfo-api-sync
#   description: ...
#   pre-pr:
#     command: .claude/skills/ocfo-api-sync/scripts/audit.sh
#     when-paths: [server/handler.go, endpoint/, model/, openapi/, postman/]
#     fail-on: 'missing [1-9]|stale [1-9]|mismatch [1-9]'
#     fix: 'Run Phase B, then Phase C, and re-audit'
#   ---
#
#   command     (required) run from the repo root
#   when-paths  (optional) run the check only when the branch touches one of these;
#               absent means always run
#   fail-on     (optional) POSIX ERE matched against the command's combined
#               stdout+stderr. A match means FAILED regardless of exit status
#   fix         (optional) one line telling the operator how to close the drift
#
# `fail-on` is the load-bearing part. Audit-style scripts routinely exit 0 while
# reporting drift on stdout — ocfo-api-sync's own audit.sh documents exactly that
# ("0 = ran successfully (drift may still be reported — read it)"). Gating on exit
# status alone would sail straight past it. The regex makes the pass/fail call
# deterministic and keeps it out of the model's judgment.
#
# Choosing the regex is the part that goes wrong. It must match ONLY when the check
# genuinely fails, which usually means a summary count rather than a section header.
# ocfo-api-sync is the cautionary case: it prints `## MISSING` / `## STALE` /
# `## METHOD-MISMATCH` headers unconditionally with `(none)` beneath them when clean,
# and its closing advice mentions MISSING and MISMATCH by name — so the obvious
# `^(MISSING|STALE|METHOD-MISMATCH)` fires on every clean run. Its stderr summary
# line (`... missing 0 · stale 0 · mismatch 0`) is the only honest signal, hence the
# count-based regex above. Always dry-run a new fail-on against a KNOWN-CLEAN tree
# first and confirm it does not match.
#
# Source with:
#   source "$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../../_lib/repo-checks.sh"
#
# The `cd -P` matters for the same reason it does in worktree.sh: these skills are
# reached through a symlink at the skill-directory level, so a plain relative `../..`
# climbs out into ~/.config/opencode/skills and never finds _lib.

# Skills with no `pre-pr:` block whose name or description matches this are printed
# as candidates for the operator to judge — never as a gate. Keeps the feature useful
# in a repo that has declared nothing yet.
REPO_CHECK_CANDIDATE_RE='drift|sync|audit|generated|codegen|schema|spec|openapi|out.of.date|stale'

# --- Frontmatter parsing -----------------------------------------------------

# Emit KEY<TAB>VALUE records for one SKILL.md. Keys: NAME, DESCRIPTION,
# PREPR_COMMAND, PREPR_WHENPATH (repeatable), PREPR_FAILON, PREPR_FIX.
#
# Deliberately a small hand-rolled YAML subset, not a real parser: these skills must
# run on a stock macOS box with no yq/python guarantee. It understands exactly the
# shapes the contract above documents — flat `key: value` at one indent level, plus
# when-paths as either an inline `[a, b]` flow sequence or an indented `- item` block
# sequence. Anything fancier is out of contract and is ignored rather than guessed at.
_repo_check_parse() {
    awk '
    function trim(s)      { sub(/^[[:space:]]+/, "", s); sub(/[[:space:]]+$/, "", s); return s }
    function unquote(s,  q) {
        q = substr(s, 1, 1)
        # \047 is a single quote — writing it literally would fight the shell quoting.
        if ((q == "\"" || q == "\047") && substr(s, length(s), 1) == q && length(s) > 1)
            s = substr(s, 2, length(s) - 2)
        return s
    }
    function valof(line) { sub(/^[^:]*:/, "", line); return unquote(trim(line)) }
    function emit_paths(v,   n, i, parts) {
        sub(/^\[/, "", v); sub(/\]$/, "", v)
        n = split(v, parts, ",")
        for (i = 1; i <= n; i++) {
            p = unquote(trim(parts[i]))
            if (p != "") print "PREPR_WHENPATH\t" p
        }
    }

    NR == 1 { if ($0 != "---") exit; infm = 1; next }
    !infm   { exit }
    /^---[[:space:]]*$/ { exit }

    # A key at column 0 closes whatever nested block we were in.
    /^[^[:space:]#]/ {
        inpre = 0; inlist = 0; indesc = 0
        if ($0 ~ /^pre-pr:/)      { inpre = 1; next }
        if ($0 ~ /^name:/)        { print "NAME\t" valof($0); next }
        if ($0 ~ /^description:/) {
            v = valof($0)
            # `description: >-` / `|` folds the value onto the following indented lines.
            if (v == ">-" || v == ">" || v == "|" || v == "|-" || v == "") { indesc = 1; desc = "" }
            else { print "DESCRIPTION\t" v }
            next
        }
        next
    }

    indesc {
        line = trim($0)
        if (line != "") desc = (desc == "" ? line : desc " " line)
        next
    }

    inpre {
        if ($0 ~ /^[[:space:]]+command:/)  { print "PREPR_COMMAND\t" valof($0); inlist = 0; next }
        if ($0 ~ /^[[:space:]]+fail-on:/)  { print "PREPR_FAILON\t"  valof($0); inlist = 0; next }
        if ($0 ~ /^[[:space:]]+fix:/)      { print "PREPR_FIX\t"     valof($0); inlist = 0; next }
        if ($0 ~ /^[[:space:]]+when-paths:/) {
            v = valof($0)
            if (v == "") { inlist = 1 } else { emit_paths(v); inlist = 0 }
            next
        }
        if (inlist && $0 ~ /^[[:space:]]+-[[:space:]]/) {
            sub(/^[[:space:]]+-[[:space:]]+/, "", $0)
            p = unquote(trim($0))
            if (p != "") print "PREPR_WHENPATH\t" p
            next
        }
    }

    END { if (desc != "") print "DESCRIPTION\t" desc }
    ' "$1"
}

# --- Path matching -----------------------------------------------------------

# True when <file> matches <pattern>.
#
# Patterns are bash `[[ == ]]` patterns, in which `*` is an ordinary wildcard that
# DOES cross `/` (unlike pathname expansion in the shell). So `openapi/**` and
# `openapi/*` are equivalent here, and both match `openapi/nested/thing.yaml`. A
# pattern with no wildcard also matches as a directory prefix, so a bare `openapi`
# or `openapi/` covers everything beneath it.
_repo_check_path_matches() {
    local file="$1" pat="$2"
    [[ -z "$pat" ]] && return 1
    pat="${pat%/}"
    [[ "$file" == $pat ]] && return 0
    [[ "$file" == $pat/* ]] && return 0
    return 1
}

# Echo one path per line for everything git reports as changed in the working tree:
# staged, unstaged and untracked.
#
# `-uall` is load-bearing. Without it git collapses an entirely-untracked directory
# into a single `?? server/` entry, and a when-paths pattern naming a file inside it
# (`server/handler.go`) would silently never match — the check would be skipped on
# exactly the branch that most needs it.
#
# The sed chain, in order: drop the 3-char status prefix (`cut`-style, so paths with
# spaces survive), keep only the destination half of a rename (`R  old -> new`), and
# unquote the path git quotes when it contains unusual characters.
repo_check_worktree_files() {
    git status --porcelain=v1 -uall 2>/dev/null \
        | sed -e 's/^...//' -e 's/^.* -> //' -e 's/^"\(.*\)"$/\1/'
}

# Echo the files this branch changes, one per line: the three-dot diff against the
# default branch plus anything uncommitted. Used when the caller has not already
# computed a file list of its own.
#
# Three-dot (origin/<default>...HEAD) is the diff against the merge-base — the same
# set GitHub shows in the PR. Uncommitted files are folded in because the calling
# skills may be about to commit them.
repo_check_changed_files() {
    local default="${1:-}"
    if [[ -z "$default" ]]; then
        default=$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null | sed 's|^origin/||')
        if [[ -z "$default" ]]; then
            default=$(git show-ref --verify --quiet refs/heads/main && echo main || echo master)
        fi
    fi
    {
        git diff --name-only "origin/$default...HEAD" 2>/dev/null || true
        repo_check_worktree_files
    } | sed '/^$/d' | sort -u
}

# --- Discovery ---------------------------------------------------------------

# Print the "=== REPO-LOCAL PRE-PR CHECKS ===" section.
#
#   emit_repo_checks_section <changed_files_file|""> <skill_name> [default_branch]
#
# <changed_files_file> is a file holding one changed path per line; pass "" to have
# this compute it. <skill_name> only shapes the `run:` line so the operator is told
# the shim path that belongs to the skill they are actually running.
emit_repo_checks_section() {
    local files_file="$1" skill_name="${2:-git-pr}" default="${3:-}"
    local root
    root=$(git rev-parse --show-toplevel 2>/dev/null) || return 0

    echo "=== REPO-LOCAL PRE-PR CHECKS ==="

    if [[ ! -d "$root/.claude/skills" ]]; then
        echo "(no .claude/skills in this repo — nothing repo-local to check)"
        return 0
    fi

    local tmp_files=""
    if [[ -z "$files_file" || ! -f "$files_file" ]]; then
        tmp_files=$(mktemp)
        repo_check_changed_files "$default" > "$tmp_files"
        files_file="$tmp_files"
    fi

    local found=0 candidates=()
    local skill_md name desc command failon fix paths
    for skill_md in "$root"/.claude/skills/*/SKILL.md; do
        [[ -f "$skill_md" ]] || continue

        name=$(basename "$(dirname "$skill_md")")
        # Reset every field per skill. Without this a skill that declares no pre-pr:
        # block would inherit the previous skill's command and be reported as a check.
        desc=""; cmd=""; failon=""; fix=""; paths=()

        local k v
        while IFS=$'\t' read -r k v; do
            case "$k" in
                NAME)            [[ -n "$v" ]] && name="$v" ;;
                DESCRIPTION)     desc="$v" ;;
                PREPR_COMMAND)   cmd="$v" ;;
                PREPR_FAILON)    failon="$v" ;;
                PREPR_FIX)       fix="$v" ;;
                PREPR_WHENPATH)  paths+=("$v") ;;
            esac
        done < <(_repo_check_parse "$skill_md")

        if [[ -z "$cmd" ]]; then
            if [[ "$name $desc" =~ $REPO_CHECK_CANDIDATE_RE ]]; then
                candidates+=("$name — ${desc:0:150}")
            fi
            continue
        fi

        found=1

        # Relevance: which declared path pattern, if any, the branch actually touches.
        local required=1 reason="no when-paths declared — always runs" hit=""
        if [[ ${#paths[@]} -gt 0 ]]; then
            required=0
            local f p
            while IFS= read -r f; do
                [[ -n "$f" ]] || continue
                for p in "${paths[@]}"; do
                    if _repo_check_path_matches "$f" "$p"; then
                        required=1; hit="$p"; reason="diff touches $f"
                        break 2
                    fi
                done
            done < "$files_file"
            [[ $required -eq 0 ]] && reason="diff touches none of: ${paths[*]}"
        fi

        if [[ $required -eq 1 ]]; then
            echo "  $name  [REQUIRED — $reason]"
        else
            echo "  $name  [skipped — $reason]"
        fi
        echo "    run:      bash \"$(dirname "${BASH_SOURCE[0]}")/../$skill_name/scripts/repo-check.sh\" run $name"
        echo "    command:  $cmd"
        [[ -n "$failon" ]] && echo "    fail if output matches:  $failon"
        [[ -n "$fix"    ]] && echo "    fix:      $fix"
        [[ -n "$hit"    ]] && echo "    matched:  $hit"
        echo ""
    done

    [[ -n "$tmp_files" ]] && rm -f "$tmp_files"

    if [[ $found -eq 0 ]]; then
        echo "(no skill in .claude/skills declares a pre-pr: block)"
    fi

    if [[ ${#candidates[@]} -gt 0 ]]; then
        echo "  CANDIDATES (no pre-pr: block — judge relevance against the diff yourself,"
        echo "  and offer to add a pre-pr: block if one of these should have gated this PR):"
        local c
        for c in "${candidates[@]}"; do
            echo "    $c"
        done
        echo ""
    fi

    return 0
}

# --- Running -----------------------------------------------------------------

# Run one declared check and decide pass/fail.
#
#   run_repo_check <name>
#
# Exit: 0  passed
#       1  FAILED — fail-on matched, or the command itself exited non-zero
#       2  not runnable — no such check, no pre-pr: block, or command missing
run_repo_check() {
    local want="$1"
    local root
    root=$(git rev-parse --show-toplevel 2>/dev/null) || { echo "ERROR: not in a git repository"; return 2; }

    if [[ -z "$want" ]]; then
        echo "ERROR: no check name given"
        return 2
    fi

    local skill_md="$root/.claude/skills/$want/SKILL.md"
    if [[ ! -f "$skill_md" ]]; then
        echo "ERROR: no repo-local skill '$want' (looked for .claude/skills/$want/SKILL.md)"
        return 2
    fi

    local cmd="" failon="" fix="" k v
    while IFS=$'\t' read -r k v; do
        case "$k" in
            PREPR_COMMAND) cmd="$v" ;;
            PREPR_FAILON)  failon="$v" ;;
            PREPR_FIX)     fix="$v" ;;
        esac
    done < <(_repo_check_parse "$skill_md")

    if [[ -z "$cmd" ]]; then
        echo "ERROR: skill '$want' declares no pre-pr: command in its frontmatter"
        return 2
    fi

    echo "=== REPO-LOCAL CHECK: $want ==="
    echo "\$ $cmd"
    echo ""

    local out status
    # Combined stdout+stderr: audit scripts commonly put the summary counts on stderr
    # and the drift report on stdout, and fail-on has to see both.
    out=$(cd "$root" && eval "$cmd" 2>&1)
    status=$?

    printf '%s\n' "$out"
    echo ""

    if [[ $status -ne 0 ]]; then
        echo "RESULT: FAILED — command exited $status"
        [[ -n "$fix" ]] && echo "FIX: $fix"
        return 1
    fi

    if [[ -n "$failon" ]] && printf '%s\n' "$out" | grep -Eq "$failon"; then
        echo "RESULT: FAILED — output matched fail-on /$failon/"
        [[ -n "$fix" ]] && echo "FIX: $fix"
        return 1
    fi

    echo "RESULT: PASSED"
    return 0
}
