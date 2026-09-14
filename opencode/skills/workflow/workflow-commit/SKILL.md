---
name: workflow-commit
description: Use for the /commit workflow command. Perform a compact issue/evidence handoff, then delegate Git mechanics to the existing git-commit skill.
---

# Commit: preserve the reviewed result

Read `{{WORKFLOW_ROOT}}/tracking/WORKFLOW.md` once. If an issue is supplied, load
`handoff.py packet ISSUE --stage commit` with exact Review/Verification URLs. Use the
compact readiness view, then run `handoff.py gate ISSUE --plan PLAN_URL --review REVIEW_URL`.
The gate requires applicable v2 review/check evidence, current contract, and no partial
staging. Missing local evidence requires real re-verification, not a fabricated receipt.
If code changed, name the delta and recommend fresh review. Content identity survives
committing the same complete bytes/modes; HEAD provenance is recorded separately.

Use the existing **git-commit** skill at
`{{WORKFLOW_ROOT}}/skills/git/git-commit/SKILL.md` for all Git mechanics and normal
native-question confirmation. Inspect status, the intended diff, and recent history;
stage only intended files. Do not re-read ticket research or re-run verified tests
when neither code nor assumptions changed. Small-task target: under a minute.

Default workflow order is review pass → commit. If the user explicitly requests an
earlier/WIP commit, honor the Git request but preserve outstanding findings and do
not describe it as review-ready. A plain `/commit` without an issue still uses the
Git skill; do not invent a ticket or new approval ceremony.

Return the commit SHA, associated issue/review links when present, and the actual
readiness state. A local commit is not a push, PR, merge, or Done status. GitHub PR
publication, merge and cleanup continue to use the existing separate Git skills.
After a normal reviewed commit, confirm readiness still holds for the committed
content. An explicitly requested WIP commit may retain failed gates, but must be
reported as not review-ready rather than silently promoted to pass.
