---
description: Turn verified research into a concrete implementation and acceptance plan.
agent: workflow-plan
model: openai/gpt-6-astra
variant: medium
subtask: true
---

Load the `workflow-plan` skill. Arguments identify the GitHub issue and optionally
the exact Research comment. Reuse valid evidence instead of repeating research.
Use the native question tool for decisions. Return the exact plan URL and stop.

$ARGUMENTS
