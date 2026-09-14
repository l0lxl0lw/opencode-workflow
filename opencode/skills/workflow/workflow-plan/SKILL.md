---
name: workflow-plan
description: Use for /plan on a GitHub issue. Reuse verified research and define implementation steps plus an observable acceptance matrix before editing code.
---

# Plan: make correctness explicit

Read `{{WORKFLOW_ROOT}}/tracking/WORKFLOW.md` once. Load
`handoff.py packet ISSUE --stage plan --include RESEARCH_URL` when supplied.
Resolve ambiguous artifacts and check later discussion/issue edits. Set Planning
without regressing active implementation/review. Small-task target: 2–4 minutes.

1. Reuse the Research artifact. Spot-check the exact route, core persistence/logic,
   and test pattern. If its source commit differs, inspect the diff in the cited
   files and update only invalidated findings. Do not repeat broad research or launch
   the specialist pipeline again. Delegate only a named unresolved question.
2. Before implementation, produce a small **acceptance matrix**:
   input/scenario → observable response → state change/no-change → proving test.
   Cover happy path and material negative/edge cases for this feature. For a DB API,
   distinguish malformed input from forbidden/missing resources, establish trusted
   identity and ownership keys, test NULL/default rows, and verify actual HTTP wiring.
   Use real valid IDs in successful fixtures; do not let fake IDs bypass validation.
   For inherited booleans/defaults, include both values and subsequent default changes.
   Apply only dimensions relevant to the task; do not add unrelated features.
3. Ask one focused batch for unresolved product choices. Recommend the minimal
   repository-consistent option. Resolve material decisions before finalizing.
4. Write a short executable plan: exact artifact/source references; decision matrix;
   affected components; 2–4 implementation steps; targeted tests and required repo/CI
   checks; documented baseline failures; manual checks only where genuinely needed.
   Separate required acceptance from optional coverage improvements. Avoid long code
    sketches, duplicate architecture essays, or full-suite reruns without a reason.

Before publication, perform one completeness self-check: does every required contract
ID have a proving check or a justified manual-review mapping? Are negative responses,
identity/state invariants, realistic fixtures, normalization, interface consumers and
documentation assumptions explicit where relevant? Do not add another planning agent
by default; request an independent plan audit only for a named consequential uncertainty.

Use `{{WORKFLOW_ROOT}}/schemas/plan.example.json` to publish a v2 **Implementation plan** with
`handoff.py record ISSUE plan --data TEMP.json --input RESEARCH_URL`. Reference the
current contract revision, exact research fact IDs, steps, coverage map and approved
`check_manifest`. Read existing repository `.opencode/workflow/checks.json` definitions
when present; choose actual affected checks rather than copying example paths. Record
justified baseline exclusions separately. Do not create/edit the repository manifest
during read-only planning. `{{WORKFLOW_ROOT}}/tracking/references/records.md` explains runner formats.
Explicitly supersede an old plan. Set Ready when prepared; Ready is not approval.

Return the exact plan URL and `/execute ISSUE_URL PLAN_URL`. Stop. The user's
explicit `/execute` of the identified plan supplies implementation authorization;
do not require an extra ceremonial approval round for an already clear plan.
