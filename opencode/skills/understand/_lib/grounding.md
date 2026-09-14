# Grounding: read the real thing first

Shared prerequisite for every skill in `understand/`. Follow this **completely** before the first
user-facing sentence — before an explanation, before a question, before judging anything the user
says.

## Scope: topic and path

Every skill here is invoked as `/<skill> <topic>` and optionally takes a path:
`/quiz-me order processing /path/to/backend`.

- **No topic** → ask what to work on. One question, then proceed.
- **No path** → use the current working directory.

## The rule

**Never explain, quiz, or evaluate from memory.** Knowing the concept in general is not knowing
*this* implementation, and the gap between the two is exactly where the user's misunderstanding
lives. A statement that is true of three-way matching in the abstract, or of Postgres in the
abstract, is worthless here if this codebase does it differently — and it usually does.

If the topic genuinely has no implementation in this repo, say so explicitly and offer to work on
general principles instead. Do not silently substitute textbook knowledge for the real thing.

## What to read, in order

1. **The implementation.** The services, handlers, and queries that actually execute. Start at the
   entry point and follow the path to the write.
2. **The schema.** For every table involved: column name, type, nullability, default, FK target,
   and every `CHECK` vocabulary **quoted verbatim** — the legal values matter more than the column
   name. Read the indexes too, including partial-index predicates, which encode uniqueness rules
   that are invisible from the table definition alone.
3. **The write path.** Which function writes which column — and, critically, **which columns exist
   but are never written by anything**. A dead column is a trap for anyone reasoning from the
   schema alone.
4. **The read path and derivations.** What is computed at query time rather than stored, and the
   exact formula, including the row filters on each side (`deleted_at IS NULL`, status exclusions).
5. **Concurrency and transaction boundaries.** Which locks are taken, in what order, under which
   isolation level, and which values are advisory versus revalidated under the lock.
6. **The failure surface.** Error codes, exception rows, what is blocking versus informational, and
   which failures surface only at runtime while the build stays green.
7. **The design docs and specs — last.** They are evidence of *intent*, not of behaviour.

## The ground-truth sheet

Before saying anything, write down — as working notes, not necessarily shown to the user:

- **Entities and grain.** What is one row of each table, and at what grain relationships are tracked.
- **Every vocabulary with its exact legal values**, in the order the code ranks them if order matters.
- **Every invariant**, and how it is enforced: by database constraint, by application code inside a
  transaction, or not at all.
- **Every derived value** and its formula, with the filters.
- **Every deliberate exclusion** — what the system refuses to do — and the stated reason.
- **Every divergence** between a design doc and the code.
- A `relative/path.ext:LINE` for each of the above.

Anything you cannot attach a `file:line` to is something you are assuming. Either go find it or
mark it explicitly as unverified when you speak.

## When the spec and the code disagree, the code wins

A design document describes what someone intended to build. Explaining or quizzing from it teaches
the user something that is no longer true — the most expensive kind of error, because it is
confidently held and survives code review.

**State the divergence out loud before proceeding.** It is usually the single most interesting
thing about the topic: it marks where reality pushed back on the design, and understanding *why*
the implementation moved is understanding the constraint that moved it.

## Rejected alternatives are the richest material in the repo

Comments of the form *"not X, because Y"*, *"deliberately NOT written"*, *"why columns and not a
junction table"*, *"this is not optional to handle"* are worth more than any amount of prose. They
give you, in one paragraph:

- the correct mechanism,
- the plausible-but-wrong alternative a reader will assume,
- and the concrete case that distinguishes them.

That is precisely the shape of both a good quiz distractor and a good hole to poke.

## Red flags

| Thought | Reality |
|---------|---------|
| "I know how three-way matching / auth / caching works" | You know the pattern. You do not know this implementation. Read it. |
| "The design doc covers it thoroughly" | The doc is intent. The code is behaviour. Read both; trust the code. |
| "The column name makes its purpose obvious" | Columns exist that nothing writes, and columns whose name predates their meaning. Find the writer. |
| "The enum values are the obvious ones" | Quote the CHECK constraint. Guessed vocabularies produce confidently wrong teaching. |
| "I have enough to start explaining" | If you cannot cite file:line for the invariants, you have enough to start guessing. |
