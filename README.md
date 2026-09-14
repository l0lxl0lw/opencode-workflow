# OpenCode workflow resources

A self-contained, configurable workflow for OpenCode:
`/ticket → /research → /plan → /execute → /review → /commit`.
It includes fresh-stage agents, bounded research specialists, Git and explanation
skills, GitHub issue handoffs, content-bound verification, and optional Orca
coordination. No default GitHub owner or board is configured.

## Install and start

Requirements: **Python 3.10+**, Git, and [OpenCode](https://opencode.ai) with a
configured model provider. Install [GitHub CLI](https://cli.github.com) and run
`gh auth login` for issue-based work. Bash is needed by the Git skill scripts.
macOS and Linux are supported; tracking uses POSIX file locking.

Clone this repository (or your fork) anywhere, then from its root run:

```sh
python3 workflow.py install --model YOUR_PROVIDER/YOUR_MODEL
python3 workflow.py doctor
python3 workflow.py prepare
```

Choose a real model ID from `opencode models`. Installation creates private local
settings and a small `~/.local/bin/opencode-workflow` launcher, refusing to replace
existing files. Add that directory to `PATH`, then **from your application repo**:

```sh
opencode-workflow launch
# or, without installing a wrapper:
python3 /path/to/opencode-workflow/workflow.py launch
```

Select the `workflow` agent and start `/ticket`. Quit and restart OpenCode after
changing settings or updating resources. No commit/push is authorized by setup
or by `/execute`; Git operations require a separate request.

See [complete setup and configuration](opencode/docs/setup.md) for GitHub Projects,
issue-only mode, private skills, model profiles, alternate paths, IDE launch,
updates, conflicts and uninstall. [The workflow contract](opencode/tracking/WORKFLOW.md)
and [operations reference](opencode/tracking/references/operations.md) describe
stage behavior. `{{WORKFLOW_ROOT}}` in resource templates is expanded by the
launcher; raw templates are not intended for direct global installation.

To remove the installed launcher, run `python3 workflow.py uninstall` from this
checkout (add `--bin-dir PATH` for a custom installation). Settings and state are
preserved; see the setup guide for optional cleanup.

## Development and checks

```sh
python3 -B -m unittest discover -s opencode/tests -p '*_test.py'
git diff --check
```

Tests use temporary homes and local Git repositories; GitHub/Orca mutations are
mocked. `opencode/tests/runtime_smoke.py` and `workflow_smoke.py` are separate,
opt-in **paid model** checks requiring a compatible OpenCode runtime and configured
models. Unit tests do not prove live provider inference, native permissions, or
GitHub project writes. See [verification scope](VERIFICATION.md).

## Attribution and license

Commands and specialist agents are derived from
[Cluster444/agentic](https://github.com/Cluster444/agentic).
See [provenance](opencode/tracking/UPSTREAM.md) and the preserved
[upstream MIT license](opencode/tracking/LICENSE.agentic).
The repository also retains its existing [MIT license](LICENSE).
Required copyright notices are legal attribution, not runtime configuration;
keep both notices when redistributing copies or substantial portions.
