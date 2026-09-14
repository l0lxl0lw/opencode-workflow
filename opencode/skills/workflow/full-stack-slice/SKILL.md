---
name: full-stack-slice
description: Use for cross-repository UI-to-API-to-database feature acceptance, paired environments, or parallel vertical-slice development.
---

# Full-stack slice contract

Use the project's private environment-adapter skill for actual paths, credentials,
ports and startup commands. Never embed those values into this public workflow.
An unavailable adapter is a setup blocker, not permission to improvise shared resources.

Extend the existing six stages:

1. Ticket: user role, page/control, initial fixture, action, visible and persisted result.
2. Research: verify control → hook → BFF/direct API → handler → service → SQL → UI
   readback. Name permission gates, mocks, caching, external dependencies and async work.
3. Plan: paired checkouts, API contract identity, fixture/reset policy, independent
   environment lease, browser scenario and negative cases, plus repository checks.
4. Execute: real browser action, network expectation, DB assertion, refreshed/reloaded UI.
5. Review: inspect both diffs; verify evidence against BOTH current content identities,
   running processes, fixture generation and declared external state. API-only tests or
   mock-backed screenshots do not satisfy full-stack acceptance.
6. Commit: retain linked repository identities and integration order. Git authorization
   remains separate; a passing browser test does not authorize a commit or deployment.

Record the adapter's receipt freshness check as a required script check in the approved
repository check manifest. Its success marker must appear only after actual identity and
DB postcondition checks. Declare the external receipt/scenario/adapter inputs; do not reuse
the generic runner receipt across external-state changes. A fresh adapter check is required
at review because the generic runner cannot fingerprint a second repository or live DB.

Keep raw traces, logs, screenshots, credentials and machine locations in private state.
Public handoffs contain sanitized outcomes and opaque evidence identities only. Missing,
failed or stale browser proof blocks the full-stack criterion without erasing separately
passing backend/UI unit checks.
