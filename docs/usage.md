# agent-orc usage

## Install

From this repository:

```bash
uv sync --group dev
```

Or install the package (editable or from a published distribution) so `agent-orc` is on your `PATH`.

Requires `git` and (for shipped example gates / e2e) `gh`. Provider CLIs (cursor-agent / grok / opencode) must be on `PATH` when not overridden in the target project’s config.

## Target project

agent-orc is subservient to the project you point at:

| In the target repo | Role |
|--------------------|------|
| `.orc/config.yaml` | Defaults (merge base) |
| `.orc/config.local.yaml` | Local deep-merge override (gitignored in projects) |
| `.agents/skills/<skill>/` | Skill bodies agents must be able to find |
| `.orc/scripts/` (optional) | Gate / issue-list helpers referenced by config |

This package ships **examples only** under [`examples/`](../examples/) — copy them into a project’s `.orc/` (and keep skills in that project). Running agent-orc with cwd = this repo (no `.orc/`) fails by design.

## Run

Always name the target repo (or `cd` there so cwd is that repo):

```bash
uv run agent-orc --repo-root /path/to/project                 # daemon
uv run agent-orc --repo-root /path/to/project --yes           # all enabled; no multi-select
uv run agent-orc --repo-root /path/to/project -n 3 --yes      # each slot × 3, then exit
uv run agent-orc --repo-root /path/to/project \
  --agents issue-workflow-review-agent -n 1
```

| Flag | Meaning |
|------|---------|
| `--repo-root PATH` | Git repository to work in (default: cwd) |
| `--config-dir PATH` | Directory with `config.yaml` (default: `<repo-root>/.orc`) |
| `--yes` | Skip multi-select; run all enabled agents |
| `--agents a,b` | Run only these agent names |
| `-n N` | Each parallel slot runs N times, then exit (omit = daemon) |

Startup multi-select (TTY, no `--yes`/`--agents`) defaults to every enabled agent checked.

## Lifecycle

Per slot (in parallel, staggered by 5s): gate → optional issue claim → pull → worktree → agent CLI → release claim → delete worktree → cooldown → repeat. `parallel_run` defaults to 1. Cooldown and gate backoff are per slot (defaults 10s, then 10→20→40→60s). The planner example waits 3600s after each run. Gate misses and claim misses do not count toward `-n`.

Worktrees and logs live **under the target project** (typically `.orc/worktrees/`, `.orc/logs/`).

## Shutdown

Ctrl-C with running agents: warn and confirm (TTY). Confirm or second Ctrl-C / non-TTY: delete tracked OpenCode sessions (`opencode session delete <id>`), kill agent process groups, and purge worktrees. Exit code **130**. OpenCode runs are started with a bound `--session` id so a restarted OpenCode server cannot respawn a killed agent.

Startup/config errors: exit **2**. Otherwise **0**, or **1** if a skill loop raised.

## Logs

Under the target project’s `.orc/logs/`: `orchestrator.log` and `.orc/logs/<agent>/run-<parallel-id>-<timestamp>.log`.

## Tests

```bash
uv run pytest -m "not e2e"
uv run pytest -m "not e2e" && uv run pytest -m e2e
```

E2e creates a `[orc-e2e]` GitHub issue on a **target project** and expects `status:accepted`. Set `ORC_E2E_REPO_ROOT` to that project (must have `.orc/config.yaml`). Needs `gh` auth and real provider CLIs. Run only when explicitly requested.

## Manual smoke

1. In a project that has skills + `.orc/`: copy [`examples/config.local.example.yaml`](../examples/config.local.example.yaml) → `.orc/config.local.yaml` if needed; point one agent at a real CLI.
2. `uv run agent-orc --repo-root /path/to/project -n 1 --agents issue-workflow-review-agent`
3. Confirm a worktree under the project’s `.orc/worktrees/` during the run, gone after.
4. Ctrl-C mid-run → confirm → processes and worktrees cleared.
