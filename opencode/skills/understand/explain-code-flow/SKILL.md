---
name: explain-code-flow
description: >-
  Explain a concept and its execution flow, or trace an existing runtime path for debugging.
  Show verified entry points and an execution-ordered call tree with relative file:line locations;
  debug mode follows concrete implementations to SQL, outbound requests and suggested breakpoints.
  Read-only. Triggers — "explain X and show me how it runs", "explain the flow of X",
  "how does X work end to end", "trace X for me", "what is the call path for X",
  "where do I set breakpoints", "I want to step through X", "how does X flow at runtime",
  "walk me through what happens when X runs", "which function actually writes this row".
---

# Explain Code Flow

One tracing procedure, with output matched to the user's intent. Answer in chat;
do not edit the project or create explanation artifacts. The renderer may consume
stdin or a temporary file outside the project.

## Choose the mode

- **Explain mode (default):** for understanding how something works end to end.
  Explain the concept, then show entry points and the execution-ordered call tree.
- **Debug mode:** for tracing, stepping through a debugger, finding breakpoints,
  or locating the query/request responsible for a result. Skip the concept lesson
  unless requested; use the full debugging output in `references/tracing.md`.
- If both are requested, give the concept explanation followed by the debugging output.

For uncommitted changes use `git-explain-diff`; for branch changes use
`git-explain-branch`. For a concept without runtime-flow intent, use
`explain-college-level`.

## Step 1 — Ground yourself in the real implementation

**REQUIRED: read `{{WORKFLOW_ROOT}}/skills/understand/_lib/grounding.md` and follow it first.** It owns topic and path resolution,
the read order, and what to extract.

## Step 2 — Explain the concept

Only in explain mode, or when explicitly requested alongside debugging:

**REQUIRED: follow `{{WORKFLOW_ROOT}}/skills/understand/_lib/explaining.md`.** Real mechanism, terminology defined inline, nothing
watered down, `relative/path.ext:LINE` on every claim.

## Step 3 — Show how it runs, in this order

1. **Call path** — the `## Entry points (N)` table: every trigger that reaches this code.
2. **Call tree** — the indented tree, ordered the way execution happens.

**REQUIRED:** Read `references/tracing.md` relative to this skill directory. It owns
the shared investigation and rendering rules: verified callers and line numbers,
concrete dispatch, execution order, the two-column spine, and side-effect leaves.
In explain mode, use its **Entry points** and **Call tree** sections; include other
sections only when they help answer the question. In debug mode, use all seven
sections in their specified order. These mode rules govern which sections to render.

Render trees with `scripts/render_tree.py` relative to this skill directory.

Every node carries a full relative `path/to/file.ext:LINE` so I can click straight into it.
