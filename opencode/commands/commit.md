---
description: Commit the intended changes with a compact, fresh-context Git handoff.
agent: workflow-commit
model: openai/gpt-5.6-luna-fast
variant: medium
subtask: true
---

Load the `workflow-commit` skill. Arguments may identify a GitHub issue and exact
Verification/Review artifacts, or simply describe the intended local commit.
Use the existing git-commit skill and native question tool. Do not push.

$ARGUMENTS
