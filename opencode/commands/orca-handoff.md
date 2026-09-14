---
description: Explicitly hand a bounded task to another Orca workspace or terminal, then return its receipt.
agent: build
model: openai/gpt-6-astra
---

Follow `{{WORKFLOW_ROOT}}/orca/COORDINATION.md` in **handoff** mode.
This invocation authorizes only the handoff described by the user.

Request: $ARGUMENTS
