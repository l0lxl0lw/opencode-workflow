---
description: Implement the approved issue plan, or fix an explicitly supplied review.
agent: workflow-execute
model: openai/gpt-6-astra
variant: high
subtask: true
---

Load the `workflow-execute` skill. Arguments identify the GitHub issue, the exact
plan when available, and optionally a Review comment to address. This invocation
authorizes the identified implementation/fix stage, not a commit or push. Ask
material questions with the native question tool; return Verification and next step.

$ARGUMENTS
