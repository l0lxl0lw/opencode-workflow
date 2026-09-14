---
description: Explicitly sync a tracked work branch with main and report its project sync state.
agent: build
model: openai/gpt-5.6-sol
---
Read `{{WORKFLOW_ROOT}}/tracking/WORKFLOW.md` and follow its contract.

Issue: $ARGUMENTS

Read the issue and helper `list` output. Verify the current worktree and branch
match the registration. This command explicitly authorizes sync for that branch.
Read the git-sync skill and its scripts from
`{{WORKFLOW_ROOT}}/skills/git/git-sync/`; use those paths rather than Claude paths,
and use the native question tool wherever it says AskUserQuestion.
Set Branch sync to Syncing immediately before the operation. Follow the skill's
rebase eligibility rules and merge fallback. Resolve conflicts with the user,
setting Conflicts when paused; never choose a side automatically or force-push
without authorization. Preserve and restore uncommitted work.
Set Verifying after integration and stash restoration, then run the repository's
relevant checks. On failure leave Verifying and report the failure. On success,
write exact commands/results to a temporary evidence file and call
`sync-state ISSUE 'Up to date' --evidence FILE`. If main moved again, report Needs
sync after ending this operation; do not start another sync without instruction.
If aborted, refresh actual ancestry and explicitly set Needs sync or Up to date
only when justified; unresolved operations stay Conflicts/Syncing. If no checks
exist, report this and ask for explicit manual verification before recording success.
Preserve the development Status throughout. Report strategy, commits, conflict
decisions, checks, remaining work and whether anything was pushed.
