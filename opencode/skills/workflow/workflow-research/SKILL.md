---
name: workflow-research
description: Use for /research on a GitHub issue. Produce bounded, source-pinned evidence for planning without mandatory multi-agent research phases.
---

# Research: answer the unknowns once

Read `{{WORKFLOW_ROOT}}/tracking/WORKFLOW.md` once. Load compact issue context with
`handoff.py packet ISSUE --stage research`, including any exact artifact links.
Read discussion for changed decisions. Set Researching only if later work is not
already active. A small-task target is 2–4 minutes, not an exhaustive repository tour.

1. List the few technical questions blocking a concrete plan. Trace the relevant
   entry point → logic → persistence and find one close implementation/test example.
   Inspect relevant ranges plus necessary callers; expand a file only when a specific
   invariant requires it. Do not scan every historical document or read whole large
   files just because a search returned them.
2. Prefer direct bounded investigation. If locating code is genuinely unclear,
   delegate one precise lookup to `codebase-locator` or `codebase-pattern-finder`.
   Use `codebase-analyzer` only for a remaining mechanism/DB/auth question. Small work
   normally needs zero or one specialist, at most two. Independent questions may run
   concurrently. Never rerun Locate → Patterns → Analyze as a mandatory pipeline.
   If nested delegation is unavailable, investigate directly rather than retrying it.
3. Verify consequential claims in source. Where applicable, record exact ownership
   keys, SQL NULL behavior, absence/idempotency semantics, error mapping, actual route
   wiring, and existing test prerequisites. Record known baseline failures from
   existing evidence; run a targeted baseline check only when necessary.
4. Stop when the contract's implementation path and verification approach are clear.
   Ask product questions through the native question tool; do not turn an assumption
   into a new requirement. A real complexity discovery can justify `--deep` scope;
   name the question and reason before expanding. No artificial minimum agent count.

Publish one v2 **Research** record using `{{WORKFLOW_ROOT}}/schemas/research.example.json` and
`handoff.py record ISSUE research --data TEMP.json --input CONTRACT_URL`. Facts have
stable IDs, concise verified claims, and 5–10 decisive source locations; the helper
binds their file hashes. Include test prerequisites and open technical questions.
Do not paste transcripts or entire source files. Explicitly supersede replaced research.
Stale facts require targeted source checks, not automatic full reinvestigation.

Return the exact comment URL and `/plan ISSUE_URL RESEARCH_URL`. Do not implement,
produce a second technical plan here, or advance project status to Planning.
