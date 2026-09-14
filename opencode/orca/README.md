# Orca integration

The installed Orca runtime owns workspaces, terminals, schedules, and its injected
OpenCode status plugin. This repository owns generic coordination and checkout-refresh
mechanics. Machine-specific paths, remotes, schedules and automation installation
instructions belong in private configuration.

## Checkout refresh

`refresh_checkout.py --path PATH --origin ORIGIN --branch BRANCH --check` checks an
explicit target without network or discard. `--apply` additionally authorizes discarding
tracked unstaged edits in that target and fast-forwarding it. It refuses staged changes,
identity mismatches, unfinished Git operations and divergent/local-only commits.
Untracked and ignored files are preserved. A post-discard failure reports partial outcome.

Use the installed Orca automation guide to configure the private target. Preserve existing
workspace/schedule/provider settings and verify the read-only precheck. Never run a
discarding refresh as an installation test.

Tests: `python3 -B -m unittest discover -s opencode/tests -p 'orca_refresh_test.py'`.

## Cross-workspace work

- `/orca-handoff`: deliver a task and stop after the accepted receipt.
- `/orca-coordinate`: supervise a Run and its worker lifecycle.

Both load [COORDINATION.md](COORDINATION.md) and live CLI guides.
