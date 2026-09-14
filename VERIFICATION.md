# Verification scope

The offline acceptance suite is:

```sh
python3 -B -m unittest discover -s opencode/tests -p '*_test.py'
git diff --check
```

| Contract | Evidence in this repository |
| --- | --- |
| Install from an arbitrary checkout/new home | `SetupTest`: relocated copy, generated executable wrapper, real subprocess launch against a fake OpenCode binary, cwd/argument/exit-status assertions |
| Preserve existing user configuration | setup collision tests, native JSONC byte preservation, runtime custom-config composition/conflict tests |
| Private skills and local model profiles | `PrivateConfigTest`, `SetupTest`: private content stays outside snapshots; all stages/specialists route to the selected model; command collisions fail |
| Generic GitHub project or issue-only operation | `IssueOnlyTest`, `TrackingTest`: selected API owner/number, real local worktree registration and freshness/sync state, skipped board mutation, malformed config failure |
| Generic, self-contained public resources | `DistributionTest`: retired-identity fingerprints, personal-home path scan, resource references, skill metadata, license bytes, Python/shell syntax and whitespace (including untracked files) |
| Existing workflow behavior | migrated tracking, handoff, packet, verification-runner, runtime and Orca regression tests |

Tests run against temporary homes and real local Git histories, with remote GitHub
and Orca writes intercepted. A fake binary proves installation and process wiring,
not native OpenCode behavior. No passing unit-test command is evidence of paid model
inference, native permission enforcement, actual board permissions or live API writes.

The optional `opencode/tests/runtime_smoke.py` and `workflow_smoke.py` use the
configured profile, start a live OpenCode server and make model calls. Run them only
when you accept provider cost and have a compatible runtime. The latter requires
nested subagents (`subagent_depth: 2` on runtimes that support that setting). These
live checks were **not run for the repository extraction**. No Windows support,
live GitHub mutation, daemon installation or end-to-end performance is claimed.

Local execution receipts can bind the actual command exits/logs to
`tracking/workflow_state.py` source fingerprints (tracked and untracked content,
executable modes and partial staging). For issue-driven work, use the normal
`verify.py` / `handoff.py` runner and publication flow with an exact approved plan.
Without an issue/plan, local test evidence is not a GitHub Review or approval.
