#!/bin/bash
# Run (or list) the repo-local pre-PR checks this repo declares.
#
# The repo declares them in the frontmatter of its own skills — see
# ../../_lib/repo-checks.sh for the `pre-pr:` contract. This is a thin entry point so
# the skill has a typeable path; all the logic lives in the shared library.
#
# Usage: repo-check.sh list           # print the checks and which ones this branch needs
#        repo-check.sh run <name>     # run one check and gate on its result
#
# Exit (run): 0 passed
#             1 FAILED — do not open/update the PR on this
#             2 not runnable (no such check, or it declares no command)

set -uo pipefail

SKILL_NAME="git-push-branch"

source "$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../../_lib/repo-checks.sh"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "ERROR: Not in a git repository"
    exit 2
fi

case "${1:-list}" in
    list)
        emit_repo_checks_section "" "$SKILL_NAME"
        ;;
    run)
        run_repo_check "${2:-}"
        exit $?
        ;;
    *)
        echo "Usage: repo-check.sh list | run <name>"
        exit 2
        ;;
esac
