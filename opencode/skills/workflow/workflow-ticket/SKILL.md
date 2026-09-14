---
name: workflow-ticket
description: Use for /ticket or an explicit request to create or refine a GitHub workflow issue. Scope the contract before research; preserve configured project and Orca tracking.
---

# Ticket: define the problem and boundaries

Read `{{WORKFLOW_ROOT}}/tracking/WORKFLOW.md` once. This stage owns product scope,
not a repository-wide technical investigation. For a small task aim for 1–2 minutes,
one batch of 3–6 decision-bearing questions, and a short issue. These are planning
targets, not permission to omit a material question.

1. Identify the user-visible outcome and classify the work as small, medium, or
   large. A bounded change through API/service/DB using existing patterns can be
   small. Do a quick local lookup only to make questions concrete.
2. Ask only what changes implementation: interface/compatibility, identity and
   access scope, invalid/absent inputs, persistence/postconditions, and verification
   where relevant. Explain and label your recommendation. Do not invent requirements
   or repeatedly expand scope to force pushback. Follow up only on real ambiguity.
3. Capture a concise contract: outcome; included/excluded behavior; acceptance
   examples with observable outcomes; decisions and rationale; unresolved technical
   questions for research. Use valid identifiers in happy-path examples and distinct
   malformed-input examples when identifiers are involved. No proposed solution is
required just to create a ticket.

After creating/refining the issue, load `handoff.py packet ISSUE --stage ticket`.
Publish a v2 contract using `{{WORKFLOW_ROOT}}/schemas/contract.example.json`:
stable requirement IDs, exact expected outcomes, constraints/exclusions, agreed
decisions and unresolved material choices. Reconcile the issue and covered comments
before copying the packet's `checkpoint_candidate`. Do not invent a digest or hide
an ambiguous decision in a summary. Use `handoff.py record ISSUE contract --data TEMP.json`
and explicitly supersede the previous contract when replacing it. Technical questions
belong in research, not in a falsely settled product decision.

## GitHub and Orca identity contract

Load the relevant identity/status section of `{{WORKFLOW_ROOT}}/tracking/references/operations.md` for
these operations; do not replay its legacy handoff examples as the v2 protocol.

Treat the request as a **new ticket** unless the user supplies the exact existing
issue or explicitly asks to update it. Similar issues are references, not permission
to edit them. Before every `gh issue edit`, show the candidate and ask with these
native choices: **Create a new ticket (Recommended)**, **Update the existing ticket**,
**Cancel**. Only the second answer authorizes updating the named issue.

For a new ticket use `gh issue create --assignee @me --body-file ...`. Check board
registration with `python3 {{WORKFLOW_ROOT}}/tracking/private_config.py --tracking-status`.
Only when `configured`, add it to the selected project using `track.py add ISSUE`,
set Status **Backlog**, and run `track.py sync-state ISSUE 'Not started'`.
`not_configured` is a supported issue-only setup: report board tracking as not
configured and continue. An invalid configuration is an error, not an absent board.
Then, only in an Orca-managed workspace, run:

```sh
python3 {{WORKFLOW_ROOT}}/tracking/track.py link-orca ISSUE
```

Use the exact URL returned by GitHub. Attempt configured-project setup and Orca attachment
independently: neither downstream failure undoes the created issue or excuses
skipping the other outcome. Verify assignment and project fields. On an Orca link
conflict, ask **Keep existing link (Recommended)** or **Replace with new issue**;
only replacement authorizes the returned `--replace-existing EXISTING_NUMBER` retry.
`not_managed` is normal outside Orca. Report `orca_unavailable`/`failed` with the
helper's exact recovery command. Only `attached`/`already_attached` proves attachment.
After successful attachment, run `track.py checkpoint-orca ISSUE Backlog` to mirror
the new-ticket milestone (the earlier status call may have preceded attachment).

For an approved existing-ticket update, preserve useful content and later work;
do not reset status/assignees or invoke `link-orca`.

Return issue creation/update, assignee/configured-project fields, and Orca attachment as separate
outcomes. Include the contract URL and `/research ISSUE_URL`. Record only a verified milestone via the existing
checkpoint helper. Do not let a tracking failure masquerade as a missing product decision.
