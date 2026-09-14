---
name: quiz-me
description: >-
  Quiz me on a concept until I demonstrably understand it. Reads the actual implementation
  first, builds ten concept questions with five variations each and multiple-choice options
  drawn from the real code, asks them as dialogs, scores at 80% to pass, then teaches whatever
  I missed and re-asks it from an angle I have not seen. Triggers — "quiz me on X", "test my
  understanding of X", "do I actually understand X", "check whether I get X", "drill me on X".
disable-model-invocation: true
---

# Quiz Me

Assess whether the user actually understands a concept **as this codebase implements it**, and
close the gap where they do not.

The output is not an explanation. It is a graded assessment, followed by targeted teaching only
where they failed. A first-pass pass produces a report card and stops.

## Invocation

`/quiz-me <topic>`, optionally with a path. Topic and path resolution, and what to do when the
topic has no implementation in this repo, are owned by `{{WORKFLOW_ROOT}}/skills/understand/_lib/grounding.md`.

Never silently fall back to textbook questions. A question answerable from general knowledge
measures nothing about whether the user understands *this* system.

## Step 1 — Ground yourself in the real implementation

**REQUIRED: read `{{WORKFLOW_ROOT}}/skills/understand/_lib/grounding.md` and follow it before writing a single question.** It owns
the contract for what to read and in what order, and what to extract — exact column vocabularies,
derived formulas, invariants and how they are enforced, locks, deliberate exclusions, and every
divergence between the design docs and the code. Questions written from memory, or from a spec
alone, are a failure of this skill: the user is being tested on *their* system, and a question
answerable from general knowledge measures nothing.

Two consequences are specific to quizzing:

- **A spec/code divergence is prime question material.** Where the implementation moved away from
  its design doc, make that one of the ten concepts. The superseded design is the most plausible
  wrong answer that exists, because it was once true.
- **Rejected alternatives are your distractors.** A comment explaining why the code does *not* do
  the obvious thing hands you the correct answer and its strongest distractor in the same
  paragraph. Collect these as you read.

## Step 2 — Pick ten concepts

Ten distinct concepts, not ten questions about one. A concept earns a slot when getting it wrong
would make the user write a bug, misread an incident, or approve a bad design. Prefer:

- **Invariants** — what is derived vs stored, and what drifts if you store it.
- **Concurrency** — which lock, what it prevents, what it degrades into without it.
- **Grain and cardinality** — and the alternative that was rejected.
- **Vocabularies with ordering semantics** — status enums, severity ranks, precedence tiers.
- **Runtime-only failure modes** — things that fail in production while the build stays green.
- **Deliberate exclusions** — what the system refuses to do, and why refusing beats guessing.

Skip anything answerable by reading a variable name.

## Step 3 — Write five variations per concept

Each concept gets five questions along a fixed taxonomy, so a missed concept can be re-asked from
a genuinely different angle rather than reworded:

|    | Variation | Tests |
|----|-----------|-------|
| **V1** | Definition | Can they state the rule? |
| **V2** | Mechanism | Can they say *why* it is built this way? |
| **V3** | Worked example | Can they run the numbers on a concrete case? |
| **V4** | Counterfactual | Can they predict what breaks if you remove it? |
| **V5** | Code-grounded | Can they explain a specific line, column, name, or SQLSTATE? |

Write all fifty **before asking anything**. A variation invented mid-quiz, after you know what
the user got wrong, drifts toward the answer they already gave.

Vary the numbers across V3 variations of the same concept. Reusing a worked example tests recall
of a previous answer, not understanding.

## Step 4 — Write the distractors

This is what decides whether the quiz measures anything. Four options per question, exactly one
correct.

**Every wrong option must encode a specific, nameable misconception.** Before writing one, finish
the sentence: *"someone picks this if they believe ___"*. If you cannot finish it, the option is
filler and the question has become a three-way guess.

Richest sources, in order:

1. Alternatives the code explicitly considered and rejected.
2. The behaviour of the *previous* version of the system — a superseded spec, a dropped column, a
   stubbed function. Plausible precisely because it was once true.
3. The standard textbook answer, where this codebase deliberately does something else.
4. The right mechanism applied at the wrong grain, or to the wrong one of two similar tables.

**Mechanical rules. A distractor failing any of these is a giveaway:**

- Match the correct option's length and specificity. The longest, most detailed option must not
  be reliably the right one.
- Every option cites something real — a column, function, constraint, or error code. The vague
  option is visibly the wrong option.
- No hedging ("might", "usually", "in some cases") that the correct answer lacks.
- No absurd options. If one is eliminable without knowing the topic, this is a three-option
  question wearing four.
- Never "all of the above" / "none of the above".

`label` is ≤ 5 words and states the position. `description` is one or two sentences carrying the
full reasoning, so that reading the options is itself worth something.

## Step 5 — Ask

Use `AskUserQuestion`. Ten questions in batches of **4, 3, 3** — one variation per concept, spread
across the taxonomy so the quiz is not five definitions in a row.

- `header` ≤ 12 characters, numbered: `Q1 grain`, `Q7 outcomes`.
- **Do not reveal correctness between batches.** Grading batch 1 before asking batch 2 tells the
  user how they are doing and changes how they answer the rest.
- Do not hint, and do not narrate your reasoning between batches.

## Step 6 — Score

One point per question. **Pass at 80% — 8 of 10.**

A concept counts as understood once the user answers *any* variation of it correctly, so the
running score is `concepts understood / 10`.

Report a card in this shape:

```
Score: 7/10 — below the 80% pass mark.

Correct   C1 edges · C2 grain · C4 locking · C5 precedence · C7 outcomes · C9 splits · C10 exceptions
Missed    C3 derived balances · C6 line-level PO · C8 signed allocations
```

For each miss, **name the misconception the chosen distractor encodes**. "You picked B, which is
wrong" teaches nothing. "You picked B, which assumes matched quantity is consumed at match time
and never released — that is the stored-balance model this schema deliberately rejects" names the
belief that has to change.

## Step 7 — Teach, then re-ask

For each missed concept, one at a time:

1. **Teach it at college level, per `{{WORKFLOW_ROOT}}/skills/understand/_lib/explaining.md`** — which owns the voice and the
   `relative/path.ext:LINE` citation requirement. Say concretely why the option they chose fails,
   with the case that breaks it.
2. **Re-ask from an unseen variation.** Missed V1 (definition) comes back as V3 (worked example)
   or V4 (counterfactual) — never a reworded V1.
3. Loop until the running score reaches 8/10.

**If a concept is missed on all five variations, stop testing it.** Five failures is a reading
problem, not a question-design problem. Teach it once more in full, point at the specific files,
and end honestly:

> "C8 (signed allocations) did not land across five variations. Read
> `service/plugin/runtime/persist.go:105-200`, then re-run `/quiz-me` on it."

Never award a pass that was not earned, and never quietly drop a concept to reach 8/10.

## Red flags

| Thought | Reality |
|---------|---------|
| "I know this concept, I can write the questions now" | You know the concept. You do not know *this* implementation. Read it. |
| "The design doc explains it well enough" | The doc is what someone intended. Quiz the code — and quiz the divergence. |
| "Three good distractors is hard, one filler is fine" | One eliminable option turns a 25% guess into 33%. Cut the question instead. |
| "They were close, I'll give it to them" | Partial credit on a four-option multiple choice is a coin flip you rounded up. |
| "They missed three — teach all three, then re-ask" | One concept at a time. Batched teaching gets skimmed. |
| "I'll write the next variation now that I see the miss" | Post-hoc variations leak the answer. All fifty exist before Q1. |
| "That was only a small slip" | Then a different variation will show it. Re-ask; do not excuse. |
