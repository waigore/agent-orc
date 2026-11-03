# agent-orc config

## Files (target project)

| Path | Role |
|------|------|
| `<repo>/.orc/config.yaml` | Project defaults (merge base) |
| `<repo>/.orc/config.local.yaml` | Deep-merge override (typically gitignored) |
| [`examples/config.yaml`](../examples/config.yaml) | Sample defaults shipped with this package |
| [`examples/config.local.example.yaml`](../examples/config.local.example.yaml) | Sample local overrides |

Load order: `config.yaml`, then deep-merge `config.local.yaml` if present. Nested maps merge; leaves in local win. After merge, every string leaf is expanded for environment placeholders (see below).

agent-orc never loads config from its own install directory. Point `--repo-root` (or cwd) at the project; optional `--config-dir` overrides `<repo>/.orc`.

## Environment substitution

Any string leaf in the merged config may use `${VAR}` or `${VAR:-default}` (no bare `$VAR`). Expansion runs once after deep-merge, before parsing.

- Unset `${VAR}` with no `:-` default → config load fails with `ConfigError` naming the variable.
- `${VAR:-default}` uses `default` when the variable is unset.
- Literals need no environment variables.
- Provider tokens `{prompt}`, `{workdir}`, `{skill}` and agent prompt tokens `{parallel_id}`, `{issue}` are filled when a run starts. Env expansion leaves them unchanged.

Primary use case: provider `--model` strings (and other argv/path/prompt values) from the environment via `.orc/config.local.yaml`. Keep secrets and machine-specific values in the environment or local config.

## Orchestrator keys

- `cooldown_seconds` (default **10**): pause after a real agent run. `0` skips the pause.
- `gate_backoff_initial_seconds` (optional): first gate-miss delay. Later misses double it. When the merged config omits it, it equals the merged `cooldown_seconds`. `0` stays `0` on every miss, so the cap does not apply and the gate runs again immediately.
- `gate_backoff_max_seconds` (default **60**): cap for that doubling.
- `stagger_seconds` (default **5**): delay between slot starts.
- `worktrees_dir` / `logs_dir`: relative to **repo root** (the target project).
- `pull_before_run` / `default_branch`: `git pull` before each worktree.

## Providers

Named command templates with `{prompt}`, `{workdir}`, `{skill}`. The orchestrator also sets process `cwd` to the worktree.

Shipped example defaults (see [`examples/config.yaml`](../examples/config.yaml)):

| Provider | Binary | Headless + workdir |
|----------|--------|--------------------|
| cursor | `cursor-agent` (not bare `agent` — that may be Grok) | `-p --force --trust --workspace {workdir} {prompt}` |
| grok | `grok` | `-p {prompt} --cwd {workdir} --always-approve` |
| opencode | `opencode` | `run --auto {prompt}` (workdir via process cwd; no `--dir` on local v2.x) |
| opencode-qwen38-max | `opencode` | `run --auto --model opencode-go/qwen3.8-max {prompt}` ([OpenCode Go](https://opencode.ai/docs/go/)) |
| opencode-deepseek-v41-flash | `opencode` | `run --auto --model opencode-go/deepseek-v4.1-flash {prompt}` |

OpenCode providers: agent-orc injects `--session <id>` when missing, then runs `opencode session delete <id>` when the run ends or on forced shutdown (before process kill — kill alone is not enough; the OpenCode server can respawn killed sessions).

Example agent→provider mapping: planner → `opencode-qwen38-max`; refine → `grok`; verify → `opencode-deepseek-v41-flash`; others → `cursor`.

## Agents

Each entry: `skill`, `provider`, `enabled`, `prompt`, optional `gate.command`, optional `parallel_run`, optional `issues.command`, and optional timing. Each timing key falls back to the orchestrator value on its own:

| Key | Fallback |
|-----|----------|
| `cooldown_seconds` | `orchestrator.cooldown_seconds` |
| `gate_backoff_initial_seconds` | `orchestrator.gate_backoff_initial_seconds` |
| `gate_backoff_max_seconds` | `orchestrator.gate_backoff_max_seconds` |

Values are numbers `>= 0`. Setting one key does not change the others.

**Skills:** `skill` names must resolve in the **target project** (typically `.agents/skills/<skill>/` with native facades). agent-orc does not ship those skills.

**Gate:** exit code **0** = pass (run agent); non-zero = miss. Omit `gate` → always pass. Stdout ignored.

**parallel_run:** integer **>= 1**. Omitted means **1** (one loop, no issue claim). Above 1, that many slots run. Each slot keeps its own cooldown and gate backoff. `-n` counts per slot.

**issues.command:** optional. Prints a JSON array of objects with `number`, the same shape as `gh issue list --json number`. Used only when `parallel_run` > 1. After the gate passes, the slot claims the **first free number in that list order** that no slot in this process owns. No free number is a claim miss: same backoff as a gate miss, no worktree, and it does not count toward `-n`. The map lives in memory for this process only. Prompt placeholders `{parallel_id}` and `{issue}` are always filled (`issue` is `none` when nothing was claimed).

Example workflow agents call [`.orc/scripts/list-status-issues.sh`](../examples/scripts/list-status-issues.sh) (copy into the project) so candidates are ordered by priority, then type, then wave, then number. That list is only a parallel lock; agents discovering with `Assigned issue: none` still judge per the project’s dispatch docs. See [project integration](project-integration.md).

Example gate (open issues that include the status label):

```yaml
gate:
  command:
    - sh
    - -c
    - test "$(gh issue list --state open --label status:pending-review --limit 1 --json number)" != "[]"
```

## Local overrides

In a project, prefer editing `.orc/config.local.yaml` only so shared `config.yaml` stays sync-friendly with templates.
