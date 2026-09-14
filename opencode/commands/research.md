---
description: Investigate the issue's concrete unknowns once and publish a compact handoff.
agent: workflow-research
model: openai/gpt-6-astra
variant: medium
subtask: true
---

Load the `workflow-research` skill. Arguments identify the GitHub issue, optional
artifact links, and optionally `--deep`. Do only this stage in this fresh context.
Use the native question tool for decisions. Return the exact Research comment URL.

$ARGUMENTS
