# Opt-in Orca coordination

Enter only through `/orca-handoff`, `/orca-coordinate`, or an explicit request to
hand off or supervise work across Orca terminals/workspaces. Ordinary workflow
commands keep their native fresh-child-session behavior.

## Load the installed contract

Resolve the session CLI using `ORCA_CLI_COMMAND` when set. For an explicitly
identified dev session use its `orca-dev`; on Linux use `orca-ide` if appropriate;
otherwise resolve `orca` on PATH. Treat this as an executable, not shell code.
Run its `status --json` and `skills get orca-cli`. Before supervised state changes,
also read `skills get orchestration --full`. Use the actual resolved executable in
every subsequent command. Load named references only for the actions needed.

These guides, shipped with the installed version, are authoritative for flags,
envelopes, handles, receipts, and recovery. If unavailable, report the blocker;
do not invent commands or fall back to retired `orchestration run` commands.
If orchestration is disabled, report the required Orca setting; do not change
experimental settings or silently downgrade supervised work to terminal prompts.

## Scope and brief

Confirm the repository and current worktree. Capture the requested outcome,
ownership/file boundaries, acceptance checks, issue URL, exact plan/review URLs,
and what edits/Git operations the user authorized. Ask only for material missing
scope. Independent implementation workers need distinct worktrees and issues;
use approved linked sub-issues rather than registering several branches to one issue.
Read-only reviewers may share the implementation checkout after edits have stopped.

Default to OpenCode unless the user selects another agent. Validate installed
agent support using the live CLI guide/help. OpenCode workers use configured
launch defaults and workflow command/agent model routing; do not pass the
Claude/Codex/Cursor-only model/effort overrides to OpenCode.

Do not assume uncommitted edits exist in a new worktree. Include exact refs and
artifact URLs, and make any required patch transfer explicit. Independent work
uses the repo's default base with no parent; stacked work needs an explicit
parent/base requested by the user. Copy full returned workspace IDs.

## Handoff mode

Create an agent-first workspace, or target the user's identified existing
terminal, using the live `orca-cli` guide. Do not create a second agent terminal
when the create receipt already supplies one. Wait for readiness before sending
where the guide requires it. Read send receipts; a timeout is not proof of failure
and must not cause duplicate delivery.

Return the workspace/branch, agent handle, and accepted delivery receipt, clearly
distinguishing input acceptance from proven turn start. Then stop. Do not create
Run/task tracking, poll completion, or claim the work itself is complete.

## Supervised mode

Use a Run, bounded Tasks, and supervised workers following the full guide. Create
dependencies only where real outputs must precede another task. Keep worker
count proportionate to independent scope; never launch multiple writers into the
same checkout. Save exact Run/Task/Dispatch IDs in the handoff summary.

Every brief must include the following worker contract, alongside the runtime's
injected preamble:

- Read the normal workflow contract when using `/research`, `/plan`, `/execute`,
  `/review`, or `/commit`. Pass exact issue and artifact URLs to stage children.
- Carry the injected Task/Dispatch/coordinator identifiers into delegated children.
  Supervised blocking questions go through `orchestration ask` to the coordinator,
  not a local unattended TUI dialog. The coordinator asks the human when needed.
- Only the owning worker sends `worker_done` once for its active Dispatch, with
  both IDs, `succeeded|failed`, actual checks, modified files, artifact URLs, and
  remaining work. Stage children report back to that worker and do not duplicate
  completion. Use the guide's heartbeat contract during long work.
- Completion of implementation is not review approval or authorization to commit,
  push, merge, or close an issue. A worker must report failure as well as success.
- A resumed worker must recover the current dispatch/preamble before reporting;
  stale IDs must not complete a later attempt.

Process every message in a Delivery before acknowledging it. Route questions and
decision gates to the appropriate owner, retaining explicit user approval for
plan changes, conflicting product decisions, and Git operations. Verify evidence
before describing a worker result as accepted. Do not infer completion from idle
terminal status or absence of output.

Release settled coordinator-owned worker terminals using `worker-release` once
their results are captured; use retained output for later inspection. Retain a
live terminal only when requested. Follow receipt recovery for ambiguous states;
never use broad terminal closure or runtime-global reset for cleanup.

Return outcomes per task, verification/artifact links, outstanding blockers, and
exact workspace/Run/Dispatch references needed to resume. Do not advance beyond
the user's requested stage or leave supervision running without reporting its state.
