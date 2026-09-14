---
name: explain-college-level
description: >-
  Explain a concept at college level — the real mechanism, correct terminology defined inline, no
  analogy standing in for the explanation — grounded in how this codebase actually implements it
  rather than how the concept works in general. Triggers — "explain X", "how does X work", "walk
  me through X", "explain X like I'm a college student".
disable-model-invocation: true
---

# Explain at College Level

Explain the concept as *this codebase implements it*, at college level.

## Step 1 — Ground yourself in the real implementation

**REQUIRED: read `{{WORKFLOW_ROOT}}/skills/understand/_lib/grounding.md` and follow it before the first sentence.** It owns topic
and path resolution, the read order, and what to extract — exact column vocabularies, derived
formulas, invariants and how they are enforced, locks, deliberate exclusions, and every divergence
between the design docs and the code.

Register alone is not what this skill is for — `{{WORKFLOW_ROOT}}/skills/understand/_lib/explaining.md` owns that, and it demands no
reading. The grounding is the difference: explaining a repo concept from general knowledge is the
failure this skill exists to prevent.

Where the code and a design doc disagree, say so before explaining. The code wins.

## Step 2 — Explain

**REQUIRED: follow `{{WORKFLOW_ROOT}}/skills/understand/_lib/explaining.md`.** It owns the voice: real mechanism, terminology defined
inline, nothing watered down, `relative/path.ext:LINE` on every claim about this codebase.

Cover the concept as a system — what the pieces are, how they relate, what the invariants are and
why they hold — and then the edge cases, the numeric consequences, and what breaks if each piece
is removed.

To have the explanation attacked instead of accepted, use `poke-holes`. To be tested on it, use
`quiz-me`. To see the runtime path as well, use `explain-code-flow`.
