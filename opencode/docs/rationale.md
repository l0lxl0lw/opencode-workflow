# Purpose and workflow decisions

## Why this project exists

Coding-agent usage limits were interrupting work in Claude Code. Moving to
OpenCode made it possible to keep the same working interface while choosing
different models. This repository provides the workflow to carry across those
choices: `/ticket → /research → /plan → /execute → /review → /commit`.

The goal is to finish with a feature that meets an explicit acceptance contract.
The workflow defines the requirements, investigates the code, plans the change,
implements it, and checks the actual result. GitHub issue handoffs carry research,
plans, and verification evidence between fresh-stage agents.

Switching models still requires checking their context handling, tool behavior,
and results. Configurable profiles make that choice practical without tying the
process to one provider's availability.

## Decisions and their basis

| Decision | Reason | Implication |
| --- | --- | --- |
| Keep model selection configurable. | Usage limits interrupted work, and execution comparisons showed different time/token tradeoffs. | Keep the stages and acceptance contract stable while evaluating model settings. |
| Use the balanced staged workflow as the basis for further experiments. | Run C passed with less recorded time and fewer reported tokens than the original command workflow in B. | Continue testing this workflow; the failed control in E shows that one pass does not establish reliability. |
| Define acceptance before implementation and review the actual change. | Fast runs and high scores still left contract defects or compilation failures. | Check observable behavior and build results; record failures and verify repairs before calling the feature complete. |
| Compare work through review and repair. | Some short runs stopped with fixes still needed. | Include fix/re-review activity and the final verdict when interpreting execution measurements. |
| Evaluate full feature slices next. | Backend experiments surfaced contract defects, while UI integration remained outside their acceptance boundary. | Extend acceptance from a user action through the API and database to visible feedback and persisted results. This is a proposed experiment. |

## Evidence from the notification-preference reset experiments

These selected results come from a supplied September 2026 benchmark summary for
one notification-preference reset task (runs A–N). They preserve the experiment
labels and reported measurements. Raw execution logs and independent assessments
are not included here, so these tables are a record of the decision inputs rather
than an independently audited or reproducible benchmark.

### Workflow comparison

These runs used the setting labeled **Sol medium**. Preparation conditions and
workflow behavior varied; the rows are not a controlled model ranking. Scores
are independent model-review scores out of 100.

| Run | Workflow | Recorded time | Reported tokens | Score | Final verdict |
| --- | --- | ---: | ---: | ---: | --- |
| A | Native Plan/Build | 11m 47s | 2,840,555* | 89 | Needs fixes |
| B | Original command workflow | 62m 22s | 20,099,941 | 99 | Pass |
| C | Balanced workflow | 42m 26s | 9,887,388 | 99 | Pass, permission-corrected |
| D | Superpowers | 16m 25s | 4,406,984 | 75 | Needs fixes |
| E | C workflow, control run | 37m 26s | 10,208,712 | 83 | Wrong denial status and compilation regression |

\* Run A includes an interrupted message with unreported usage.

Run C reported about **51% fewer tokens** than B and passed with the same score,
with a permission correction noted. That supported using C for later comparisons.
Run E then failed under the same workflow/model label, which is why acceptance
checks remain necessary on each task. A and D do not measure time to an accepted
feature: both still needed fixes when their recorded runs ended.

### Execution with shared preparation

J, K, and L reused the same C-workflow preparation: **15m 14s** and
**1,980,795 reported tokens**. The following table excludes that preparation and
compares the execution/review/repair cycles. All three passed.

| Run | Setting | Cycle time | Reported cycle tokens | Fix/re-review rounds |
| --- | --- | ---: | ---: | ---: |
| J | Sol high | 31m 59s | 8,994,752 | 1 |
| K | Sol xhigh | 20m 28s | 6,778,467 | 0 |
| L | Astra high | 23m 39s | 5,244,128 | 0 |

Astra high reported **22.6% fewer cycle tokens** than Sol xhigh and took
**3m 11s longer**. Adding shared preparation once to each task gives 7,224,923
reported tokens for Astra high versus 8,759,262 for Sol xhigh, a **17.5%**
reduction. These observations make Astra high a candidate for token-efficient
execution and Sol xhigh a candidate for faster execution in further tests.

### How to interpret the results

- This was one task with single runs per configuration. It does not establish a
  general model ranking or a reliable pass rate.
- Model names are experiment labels, not verified public provider IDs or versions.
- Reported tokens include cached input. Lower totals do not establish lower cost
  or longer subscription access.
- The shared-plan comparison had no fresh Sol-medium control. Conclusions about
  reasoning settings are therefore limited.
- Times exclude independent grading and documented operator recovery pauses.
  Zero fix rounds describes recorded review/repair activity, not zero internal
  iteration. A passing assessment does not prove the absence of bugs.
- Other runs in the supplied summary found error disclosure and rejection of a
  valid uppercase UUID. Those failures reinforce the need for concrete negative
  and boundary-case acceptance checks, even when review scores are high.

## Next experiment: end-to-end feature acceptance

The intended task boundary connects the user's action to backend behavior,
persisted state, and the visible UI result. For a reset-preferences feature:

| Part of the slice | Observable acceptance |
| --- | --- |
| User action | The user can initiate the reset from the relevant screen. |
| Authorization | The request checks the correct user and scope; denial returns the agreed response. |
| Persistence | Only the intended preferences change, without changing another user's state. |
| Feedback | The UI accurately reflects success or failure. |
| Reload | Reloading shows the persisted result; negative cases are checked too. |

Layer-level tests remain useful. The experiment is to determine whether this
broader acceptance boundary reduces integration work left over at the end.
The backend benchmark has not yet demonstrated that benefit. Further evaluation
should repeat promising settings across more tasks and record actual cost
separately from token totals.

For stage rules, see the [workflow contract](../tracking/WORKFLOW.md). For model
profiles and installation, see [setup and configuration](setup.md). For the scope
of this repository's own checks, see [verification](../../VERIFICATION.md).
