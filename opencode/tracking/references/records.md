# V2 records and evidence

These are helper-owned JSON formats, not native OpenCode configuration keys.
`packet.py` validates structure; `verify.py` runs checks; independent review evaluates
whether the contract, tests and implementation are actually sufficient.

## Ticket → contract

1. Create/update the issue only under the existing identity/authorization rules.
2. Load `handoff.py packet ISSUE --stage ticket` to obtain the current issue/discussion
   and `checkpoint_candidate`. Legacy mode retains readable old artifacts.
3. Read the covered decisions. Fill `schemas/contract.example.json` with the real
   outcome, stable requirement IDs and exact expected behaviors. Preserve exclusions,
   operational constraints and unresolved material decisions. Replace its checkpoint
   with the candidate only after reconciling the covered content.
4. Publish `handoff.py record ISSUE contract --data /approved/temp/contract.json`.
   The helper computes `revision`; callers do not invent it. Replacements require
   `--supersedes OLD_CONTRACT_URL`. Keep an already-active code/review status.

If discussion changes during this process, publication refuses the stale checkpoint.
New/edited/deleted discussion cannot disappear behind an ID-only watermark. Human edits
to a v2 body's rendering or envelope invalidate its compact representation and make
it material discussion. Do not refresh hashes without understanding the change.

## Research

Use `schemas/research.example.json`. Facts contain IDs, claims and repository-relative
locations. The helper hashes current source files; supplying an old hash catches
concurrent changes. Open technical questions are retained. Publish with `record ...
research --data ... --input CONTRACT_URL`; supersede a prior research record explicitly.
Planning can reuse facts while checking source-change flags rather than repeating a
full investigation. Facts are evidence-linked claims, not infallible truths.

## Plan

Use `schemas/plan.example.json`. Copy the contract's exact revision. Map every required
requirement ID in `coverage` to required checks or a `review_reason` for genuinely manual
evidence. Specify concrete steps. Optionally cite research facts using `facts` entries
with `artifact` and `id`. The execute packet loads only those referenced facts.

`check_manifest` is an approved snapshot of repository checks, not shell instructions
to execute while loading GitHub context. Prefer existing `.opencode/workflow/checks.json`
definitions; propose justified task-specific changes explicitly in the plan. Every
check specifies `id`, `argv` (an argument array), `kind`, `format`, and `required`.

- `kind`: test, compile, lint, static.
- `format`: go-json, unittest, script, exit. Tests require parsed results; exit-only
  compilation cannot stand in for behavioral proof. `script` is for repository-owned
  assertion scripts: declare `success_pattern` and optionally `skip_pattern` (default
  matches SKIP at line start). Zero exit without the marker is unverified. This records
  a suite assertion marker, not invented per-test counts; review the script's assertions.
- `required_tests`: exact Go test/subtest names that must report pass. A required
  check allowing optional skips must identify its mandatory tests.
- `allow_skips`: false by default. Skips do not silently satisfy required proof.
- `cwd`: repository-relative, default `.`.
- `env`: explicit non-secret configuration only. Never put credentials in the plan.
- `env_keys`: relevant inherited environment names whose values affect the checks.
  Only an opaque fingerprint is stored, not their values. Include data/schema/version
  identifiers where appropriate; changing external data still requires fresh checks.
- `timeout_seconds`: positive, default 1800. This is a declared check timeout, not
  an overall workflow token/time cutoff.

Publish `record ... plan --data ... --input RESEARCH_URL`. Existing requirements and
new later discussion remain authoritative; selecting an old URL cannot hide them.
Plan `unresolved` decisions prevent execution. Planning does not edit the application.

## Execution → recorded verification

From the actual implementation worktree after `/execute ISSUE PLAN_URL` authorization:

```
python3 {{WORKFLOW_ROOT}}/tracking/verify.py init ISSUE --plan PLAN_URL
# implement the approved change and reconcile the check manifest if needed
python3 {{WORKFLOW_ROOT}}/tracking/verify.py run ISSUE --plan PLAN_URL
python3 {{WORKFLOW_ROOT}}/tracking/handoff.py record ISSUE verification --run RUN_ID
```

`init` creates the repository manifest only if absent; an incompatible existing file
is preserved and requires deliberate reconciliation. Its intended definitions must
match the approved plan. The manifest is an application-repo configuration change,
so create it during authorized execution, not read-only planning.

`run` executes argv arrays, captures outputs privately, detects source changes during
checks, and records a content-addressed receipt. It exits nonzero if a required result
is failed, unverified or source-changed. `verify.py show RUN_ID` exposes detailed local
results and log paths. Failed runs can be published truthfully; they cannot pass the
review gate. Keep baseline failures visible, with approved required scoped checks.

`--reuse` explicitly reuses passing checks only for matching code, contract, check
definition and declared environment/toolchain fingerprints. It is not valid when
external state changed without being fingerprinted. Ordinary review reads the existing
receipt rather than executing the runner again. The content identity survives staging
and committing unchanged bytes/modes; partial-index divergence remains distinct.

Runner logs are private local evidence; GitHub verification records carry IDs and
summaries. Missing/mutated local logs require re-verification. No schema can establish
that a poorly chosen test actually proves the mapped requirement.
Receipts also bind the verifier implementation hash; a changed verifier requires
fresh checks rather than silently accepting a result parsed by different rules.

## Review → repairs → commit

Use `schemas/review.example.json`. Include the exact plan URL and current published
verification's run ID. Record all findings with stable IDs, required true/false,
severity, expected/observed behavior, location, and open/disputed/resolved status.
Resolved findings need concrete `evidence`. Required findings cannot disappear or
silently become optional in re-review; include `previous_review` and supersede it.

Manual coverage needs `manual_evidence` entries with requirement ID, observed facts,
and actual source locations. Optional improvements remain non-blocking. A material
new regression can block even if the original matrix missed it.

```
python3 {{WORKFLOW_ROOT}}/tracking/handoff.py record ISSUE review --data REVIEW.json
python3 {{WORKFLOW_ROOT}}/tracking/handoff.py gate ISSUE --plan PLAN_URL --review REVIEW_URL
```

Passing publication checks the current contract, required runner results and manual
evidence presence. The commit/readiness gate also requires the recorded review to
match current content and no partial staging. It grants no commit/push/merge authority.
Legacy review labels remain historical data, never an implicit v2 gated pass.

Repair packets omit resolved bodies and point to the full prior review for publication.
Local snapshots provide a precise repair diff when available; if absent on another
machine or too large/binary, the helper explicitly asks for direct/full-diff inspection.

## Storage and migration

Private state defaults to `~/.local/state/opencode-workflow/`, overrideable with
`OPENCODE_WORKFLOW_STATE` outside the worktree. It contains pinned resources, source
fingerprints, small changed-source blobs, repair diffs and runner logs. Treat it as
private task data. GitHub remains the durable requirements/decision record.

No automatic deletion, destructive migration, transcript compression model, or global
state reset is introduced. `context`/legacy `publish` remain for old artifacts. Use
`packet`, `record`, `snapshot-v2`, and `gate` for the new cycle. `--history` is an explicit
large-context escape hatch; default packets never silently truncate required text.
