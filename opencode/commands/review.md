---
description: Independently review actual changes and tests; return pass or actionable fixes.
agent: workflow-review
model: openai/gpt-6-astra
variant: medium
subtask: true
---

Load the `workflow-review` skill. Arguments identify the GitHub issue, optional
exact plan, and optionally a previous Review comment for a re-review. Assess the
actual diff in this fresh context. Use native questions only when necessary.
Do not edit application code. Publish a verdict and exact next command.

$ARGUMENTS
