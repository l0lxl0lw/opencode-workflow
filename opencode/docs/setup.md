# Set up your own workflow

## Prerequisites and first install

Install Python 3.10+, Git, OpenCode, and (for issue workflows) GitHub CLI. Configure
your provider using OpenCode's `/connect`, then inspect `opencode models` and select
a model you can access. Authenticate GitHub with `gh auth login`.
Orca and GitHub Projects are optional; the Agentic CLI is not required.

Clone this repository or a fork to any location. No particular directory name is
required. From its root:

```sh
python3 workflow.py install --model YOUR_PROVIDER/YOUR_MODEL
```

This creates `~/.config/opencode-workflow/config.json`, a neighboring local
`profiles.json`, and `~/.local/bin/opencode-workflow`. Files containing settings
are mode 0600. Nothing is installed into OpenCode's global directory; no credentials
are copied and no GitHub writes happen. Setup refuses existing files. For an
already-configured machine, use `install --launcher-only` to add just the wrapper.
For no wrapper, use `setup` instead of `install` and launch `workflow.py` directly.

Add `$HOME/.local/bin` to your shell's `PATH`, or use the printed launcher path.
Run `opencode-workflow doctor --github` to check binaries, resource/config
composition and GitHub authentication without model calls or GitHub mutations.
`prepare` prints snapshot metadata without requiring OpenCode to be installed.

## GitHub owner/project, or issue-only mode

For a new setup, optionally supply:

```sh
python3 workflow.py install --model YOUR_PROVIDER/YOUR_MODEL \
  --project-owner YOUR_GITHUB_USER_OR_ORG --project-number 7
```

Use your actual Projects number, not an issue number. To enable board operations,
grant appropriate GitHub CLI scopes (for example `gh auth refresh -s project`),
create/select a board, then explicitly run:

```sh
python3 /path/to/opencode-workflow/opencode/tracking/track.py configure
```

**This last command writes to the selected board.** It creates the required
`Status` and `Branch sync` single-select fields. It refuses incompatible field
options on populated projects; reconcile those manually rather than discarding
existing items. No setup command silently chooses or creates a board.

Omit `tracking` in local settings for supported **issue-only mode**. Contracts,
plans, verification and review remain GitHub issue comments. Branch registration
and freshness checks continue, but field updates are skipped. `status` reports
`not_configured`, never a false board update. Explicit board-only `add`/`configure`
operations fail without a configured target. Malformed settings are errors.

## Private skills, models and paths

Settings are this helper's format, **not** native `opencode.json`:

```json
{
  "version": 1,
  "profiles_file": "profiles.json",
  "skills_paths": ["skills"],
  "tracking": {"owner": "example-org", "number": 7}
}
```

All fields except `version` are optional. Relative paths resolve beside the
settings file. Directories/files must already exist. `setup`/`install` accept
repeated `--skills-path PATH`, `--profiles-file PATH`, or `--model PROVIDER/MODEL`
plus optional `--variant NAME`. A supplied profile replaces bundled presets.
Do not put provider tokens in profiles; authentication stays in OpenCode.

Generated profiles use one model for every stage **and specialist**, with an empty
variant meaning no named reasoning variant. For custom routing, edit your local
profile (or start from `opencode/examples/profiles.json`):

```json
{
  "version": 1,
  "default": "custom",
  "defaults": {"model": "YOUR_PROVIDER/YOUR_MODEL", "variant": ""},
  "profiles": {
    "custom": {
      "workflow-execute": {"model": "YOUR_PROVIDER/YOUR_CODING_MODEL"},
      "workflow-review": {"model": "YOUR_PROVIDER/YOUR_REVIEW_MODEL"}
    }
  }
}
```

The bundled named profiles are optional presets, not promises of model availability.
Choose `launch --profile NAME` to select a profile. Every private skill needs
`name` and `description` frontmatter in its own `SKILL.md`. Private skills remain
outside snapshots; the launcher adds native `skills.paths` and a thin slash-command
reference. Conflicting skill/command names fail rather than overwrite user entries.

Path controls:

| Setting | Default / purpose |
| --- | --- |
| `XDG_CONFIG_HOME` | `~/.config`; workflow settings live below `opencode-workflow/` |
| `OPENCODE_PRIVATE_CONFIG` | Explicit settings file (missing explicit file is an error) |
| `install --bin-dir PATH` | `~/.local/bin`; wrapper destination |
| `OPENCODE_WORKFLOW_STATE` | `~/.local/state/opencode-workflow`; resource snapshots, outside source repo |
| `OPENCODE_TRACK_STATE` | `~/.local/state/opencode-track`; branch registry |
| `OPENCODE_WORKFLOW_ROOT` | Reserved for the pinned resource root in child launches; do not set to a checkout |

Handoff/verification cache settings are described in the operations reference.
All settings and cache paths may be outside the repository, including paths with
spaces. Existing private configurations can be selected explicitly using
`OPENCODE_PRIVATE_CONFIG`; no private repository is implicitly discovered.

## Launch and coexistence

From the application repository, run `opencode-workflow launch`. OpenCode arguments
go after `--`; launcher options go before it:

```sh
opencode-workflow launch --profile custom -- serve --hostname 127.0.0.1 --port 4096
```

For an IDE, invoke `python3 /absolute/path/to/workflow.py launch -- ...` with the
application cwd and the same environment. Keep HOME unchanged. Native user
JSON/JSONC, authentication and unrelated global configuration are not rewritten.
An IDE's extra `OPENCODE_CONFIG_DIR` is composed via links; conflicting workflow
files there are reported for manual reconciliation. Workflow-named inline agents
and commands are owned by this launcher and overridden for this process.
Compatibility skill scans are disabled during workflow launches; explicitly add
the skill directories you want. Plain OpenCode remains available separately.

If migrating another resource installer, remove only its known owned links after
inspecting them; preserve real files and foreign links. Do not copy raw templates
into global catalogs. The launcher resolves resource markers into immutable,
content-addressed snapshots and retains a snapshot for nested launches.
Imported Git skill references to the standard global skill catalog are also
resolved into that snapshot, and dialog instructions use OpenCode's `question`
tool. No matching global skill links need to exist.

## Updates and uninstall

Update the checkout yourself, then quit/restart OpenCode through the launcher.
Existing sessions keep their pinned resources. Re-running setup never overwrites
local settings. If the checkout moves, remove only the generated launcher after
checking its target and rerun `install --launcher-only` at the new location.

To uninstall the generated launcher, run from the original checkout:

```sh
python3 workflow.py uninstall
# If installed with a custom destination:
python3 workflow.py uninstall --bin-dir "/path/to/bin directory"
```

The command succeeds if the launcher is already absent. It only removes an
unmodified wrapper generated for this checkout and the same Python interpreter;
symlinks, edited wrappers and launchers for other checkouts are preserved with an
error. If the checkout moved or the interpreter changed, inspect the wrapper's
target and remove it manually. Settings, private skills, state and the checkout
are preserved. Optionally remove your workflow settings and state directories after
backing up verification evidence/private skills. Do not delete native OpenCode
configuration or authentication. No daemon or scheduled job is installed. If you
want periodic freshness checks, schedule `track.py refresh` yourself; it fetches
and can post issue comments/update the explicitly configured board, never syncs
branches. Check results and permissions before scheduling.
