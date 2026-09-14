---
name: workflow-execute
description: Use for /execute on a GitHub issue and approved plan, optionally with a review to fix. Implement, verify, and publish content-bound evidence in a fresh context.
---

# Execute: implement the contract, then prove it

Read `{{WORKFLOW_ROOT}}/tracking/WORKFLOW.md` once. Load `handoff.py packet ISSUE --stage execute`,
pinning the exact plan and supplied Review with repeated `--include` arguments.
Do not infer scope from parent conversation or treat a plan's checked boxes as proof
that review findings are fixed. Resolve conflicting plans or changed product decisions.

Confirm the correct repo and isolated feature worktree. In an Orca-managed workspace,
run `track.py link-orca ISSUE` from that worktree (preserve conflicting links).
Register the issue branch,
and refresh freshness once. Ask before sync; a Needs sync indication is not permission
to rebase. `/execute` authorizes this identified plan/fix stage, not commits or pushes.
Set Implementing. Small-task implementation target: 5–12 minutes; do not sacrifice
correctness to that target. If work grows, name the concrete cause and narrow the
next investigation instead of reopening all research.

1. Read the plan's relevant code and tests, not the whole research transcript.
   Implement a coherent vertical slice using existing patterns. Keep a short todo
   list if useful. Inspect unfamiliar dirty files as possible user work before editing.
2. Add meaningful tests from the acceptance matrix. Validate the public transport
   behavior as well as service logic when relevant. Exercise real DB semantics for
   SQL-sensitive changes; mocks do not prove row isolation, NULL handling, or inheritance.
3. Run focused checks during iteration. Fix failures caused by this change. Once they
   pass, run remaining required repo/CI checks once. Preserve actual outputs/commands,
   relevant baseline failures, skipped tests, and unperformed checks. Do not fix
   unrelated baseline failures or claim that a compile-only command tested behavior.
4. If reality invalidates a material design decision, ask and record the deviation;
   do not silently change the API contract. Avoid delegation unless targeted debugging
   has a specific unanswered question. One bounded analyzer is preferable to another
   general investigation cycle.

## Review-fix invocation

If compact context contains a current changes-requested Review but the caller did
not pin it, resolve that artifact before editing. Do not blindly repeat the original
plan while leaving its known findings open.

When a Review URL is supplied, use the packet's open finding IDs and repair delta.
Treat it as a scoped repair pass against the same contract. Address actionable
findings, add missing regression cases, and record each ID as fixed/disputed/unresolved
with evidence. Fetch the full prior Review only to recover needed details and resolution
history. A disputed material finding returns to review. Inspect affected invariants
and new regressions, but do not restart research/planning unless scope actually changes.

After authorized implementation, initialize/reconcile the repository check manifest
from the exact approved plan (`verify.py init ISSUE --plan PLAN_URL`). An incompatible
existing manifest is preserved; reconcile deliberately and revise the plan when its
required definitions need to change. Run `verify.py run ISSUE --plan PLAN_URL` to record
actual exits, test/skip details, code/contract/environment fingerprints and private logs.
Do not replace the runner receipt with a prose claim. Use `--reuse` only when matching
source and declared assumptions really hold; changes to external data require fresh checks.

Publish **Verification** with `handoff.py record ISSUE verification --run RUN_ID`
(plus `--input REVIEW_URL` for fixes and `--supersedes PREVIOUS_VERIFICATION_URL`). Failed
receipts remain publishable as truthful evidence but cannot satisfy a pass. Finish code
edits before recording checks; source changes during a check invalidate its evidence.
Return finding resolutions and baseline/skipped/missing checks concisely beside the URL;
full logs remain local and fetchable with `verify.py show RUN_ID`.

Return the Verification URL and `/review ISSUE_URL PLAN_URL` (plus previous Review
URL on a repair). Implementation complete is not review pass. Stop before commit.
