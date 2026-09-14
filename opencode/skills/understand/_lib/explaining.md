# Explaining: college level, cited

Shared voice contract for every skill in `understand/`. It governs any sentence that *teaches* —
the whole of `explain-college-level` and `explain-code-flow`, the opening explanation in
`poke-holes`, and the remedial teaching in `quiz-me` after a missed concept.

## The rule

> Explain technical concepts at a college level: assume the reader is a capable adult who wants
> the real mechanism, not a simplified analogy. Use correct terminology and define it inline. Do
> not water things down or skip the parts that are hard — the full explanation is easier to
> understand than a vague one.

This file is the one copy of that wording. Every skill in `understand/` is pointed here rather than
restating it, so there is a single place to edit and nothing to keep in sync.

## What it rules out

- **An analogy standing in for the mechanism.** An analogy after the mechanism is a bonus. An
  analogy instead of it is the thing this register exists to prevent.
- **A term used without being defined.** Define it in the clause where it first appears; do not
  swap it for a vaguer word to avoid the definition.
- **Skipping the hard part** because it is long. Length is not the cost being optimised here.

## Citation

Every claim about *this* codebase carries a `relative/path.ext:LINE`. A statement with no line
behind it is either general knowledge — say so — or an assumption, per `grounding.md`.

The path is relative to the repository root and clickable in a terminal. Quote the code itself
where the wording of the code is the point: a `CHECK` vocabulary, an error string, a lock mode.
