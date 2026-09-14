---
name: poke-holes
description: >-
  Explain a concept as this codebase actually implements it, have me explain it back in my own
  words, then attack my explanation — naming every belief that is wrong, right for the wrong
  reason, or missing the condition that makes it true — and loop until a round finds no holes.
  Reads the real code, columns, values and flows first. Triggers — "poke holes in my
  understanding", "let me explain X and tell me what I'm getting wrong", "check my mental model
  of X", "explain X then grill my explanation", "am I thinking about X correctly".
disable-model-invocation: true
---

# Poke Holes In My Understanding

A four-beat loop: **I explain → you explain back → I attack your explanation → you revise.**
Repeat the last two until a round produces no substantive holes.

The value is entirely in beat three. An explanation the user reads and nods along to produces the
illusion of understanding; an explanation they have to *generate* exposes exactly which parts they
never had. This skill exists to find those parts and name them precisely.

## Invocation

`/poke-holes <topic>`, optionally with a path. Topic and path resolution, and what to do when the
topic has no implementation in this repo, are owned by `{{WORKFLOW_ROOT}}/skills/understand/_lib/grounding.md`.

## Step 1 — Ground yourself in the real implementation

**REQUIRED: read `{{WORKFLOW_ROOT}}/skills/understand/_lib/grounding.md` and follow it completely before explaining anything.** It
owns the contract for what to read and in what order, and what to extract — exact column
vocabularies, derived formulas, invariants and how they are enforced, locks, deliberate
exclusions, and every divergence between the design docs and the code.

This step is not optional politeness. **Every hole you poke in beat three must be backed by a
`file:line`.** Without the ground-truth sheet you will end up attacking the user's explanation for
disagreeing with your generic model of the concept, which is worse than not running the skill at
all: they will "correct" a belief that was right about their system.

Where the code and a design doc disagree, say so before you start explaining. That divergence is
usually where the user's mental model is stale too.

## Step 2 — Explain the concept

**REQUIRED: follow `{{WORKFLOW_ROOT}}/skills/understand/_lib/explaining.md`** — it owns the voice and the `relative/path.ext:LINE`
citation requirement. Cover the concept as a system: what the pieces are, how they relate, what
the invariants are and why they hold.

**Explain the mechanism, not every case.** Deliberately leave the edge cases, the numeric
consequences, and the "what breaks if" reasoning for them to derive. Those derivations are what
you are about to test; handing them over now means beat three finds nothing.

End the explanation by handing over the turn with an explicit scope, so they are not guessing at
how much to write:

> Now explain it back to me in your own words. Cover: what the three edges assert, where the
> allocation is tracked and why at that grain, and what happens when two bills race for the same
> receipt quantity. Don't re-read the code — I want your model, not a transcription.

Asking them not to re-read matters: an explanation reconstructed from the source measures reading
comprehension, and the point is to surface what they actually retained and believe.

## Step 3 — Attack the explanation

Decompose what they wrote into **discrete assertions** before judging any of them. Judge each
assertion against the ground-truth sheet — never against how you would have phrased it.

Assign every assertion one of four verdicts:

| Verdict | Meaning | Action |
|---------|---------|--------|
| **Wrong** | Contradicts the code. | Poke it. Highest priority. |
| **Right for the wrong reason** | Conclusion holds; the cited mechanism is false. | Poke it — this is the *most dangerous* class. |
| **Underspecified** | True, but missing the condition that makes it true. | Probe it with the case where the missing condition bites. |
| **Right** | Correct and correctly reasoned. | Say so in a few words. Move on. |

**Right for the wrong reason is the class to hunt hardest.** A false mechanism that happens to
produce correct answers on the cases seen so far survives testing, survives code review, and fails
the first time the case changes. It is invisible to any assessment that only checks conclusions,
which is precisely why this skill takes free-text explanations instead of multiple choice.

### Every hole must carry three things

1. **Their assertion, quoted verbatim.** Not paraphrased — paraphrase lets you argue against a
   claim they did not make.
2. **What the code actually does**, with `relative/path.ext:LINE`.
3. **The concrete case where their belief produces a wrong outcome.** Real numbers, a real
   sequence, a real query. *A hole with no failing case is an opinion, and you must drop it.*

Rank holes load-bearing first — the ones that would cause a bug, a misread incident, or a bad
design approval — then precision issues.

### Do not hand over the answer yet

Name what is wrong and give the failing case; **withhold the full correct mechanism until they have
had one attempt at repairing it themselves.** Explaining it immediately turns the next round into
them reading your paragraph back to you, and the repair is where the learning actually happens.

Only after a second failed attempt on the same hole do you explain it completely — and then say
plainly that you are doing so.

### Omissions are holes too, but bounded

Something they never mentioned, which is load-bearing, is a hole of a different kind — label it as
an omission rather than an error, so they can tell "I said something false" apart from "I left out
the thing that makes this work". **Cap it at the two or three most important**, otherwise the round
degenerates into the lecture this skill exists to replace.

### Never manufacture a hole

If an assertion is right, say it is right. Inventing a criticism to look rigorous teaches a false
correction and destroys the only thing that makes the skill useful: that when you say something is
wrong, it is wrong.

Corollary: **poke at beliefs, never at wording.** If the mechanism is correct but the vocabulary is
loose, offer the precise term in one clause and move on. Terminology is not a hole.

If the whole explanation is sound on the first pass, say so, name the two or three points that were
non-obvious and that they got right, and stop. A short session is a good outcome.

### Tone

Blunt, specific, not contemptuous. Attack the claim, never the person. "That is wrong, and here is
the case that breaks it" is the register; "surely you can see why that's wrong" is not.

If they write "I don't know" or a very thin explanation, do not grade it as failure. Ask which part
they want re-explained, re-explain that piece, and hand the turn back.

## Step 4 — Revise and re-attack

Close every round by naming which holes to address:

> Revise your explanation. You need to fix the grain claim and the voided-bill claim; the rest
> stands.

Then attack the revision the same way. **The session ends when a round produces no Wrong and no
Right-for-the-wrong-reason verdicts**, and at most cosmetic underspecification.

## Step 5 — Close

Finish with a short diff of the mental model — what they believed at the start of the session
versus what they believe now, in three or four lines:

```
Started believing   remaining quantity is decremented at match time
Now                 it is derived per read, and voiding a bill releases it via deleted_at IS NULL

Started believing   the bill line points at a receipt line
Now                 allocation is tracked at PO-line grain; the receipt breakdown is evidence only

Held up throughout  why positional matching is refused, and why unmatched beats wrong in AP
```

Naming what held up matters as much as naming what moved: it tells them which parts of their model
they can now build on.

## Red flags

| Thought | Reality |
|---------|---------|
| "I know this concept well enough to explain it" | You know the pattern. Read the implementation, or you will correct true statements. |
| "Their phrasing is off, I'll flag it" | Terminology is not a hole. Offer the word in a clause and move on. |
| "This feels wrong but I can't cite it" | Then it is not a hole yet. Go find the line, or drop it. |
| "I'll list every hole so they see the full picture" | Ranked, load-bearing first, omissions capped at three. An exhaustive list gets skimmed. |
| "I'll explain the fix while I point out the error" | The repair is where the learning is. Withhold the mechanism for one round. |
| "Nothing's wrong, but I should find something" | Say it's right. A manufactured hole destroys every real one that follows. |
| "They got the answer right, so that assertion passes" | Check the reasoning. Right-for-the-wrong-reason is the class this skill exists to catch. |
| "We've gone three rounds, close enough" | The loop ends on a clean round, not a round count. |
