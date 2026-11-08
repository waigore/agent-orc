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
- `schedule_poll_seconds` (default **5**): how often schedule loops re-check cron due times.
- `worktrees_dir` / `logs_dir`: relative to **repo root** (the target project).
- `pull_before_run` / `default_branch`: `git pull` before each worktree.

## Providers

Named command templates with `{prompt}`, `{workdir}`, `{skill}`. The orchestrator also sets process `cwd` to the worktree.

Shipped example defaults (see [`examples/config.yaml`](../examples/config.yaml)):

| Provider | Binary | Headless + workdir |
|----------|--------|--------------------|
| cursor | `cursor-agent` (not bare `agent` — that may be Grok) | `-p --force --trust --workspace {workdir} {prompt}` |
| grok | `grok` | `-p {prompt} --cwd {workdir} --always-approve` |
| hermes | `hermes` ([CLI](https://hermes-agent.nousresearch.com/docs/reference/cli-commands)) | `-z {prompt} --yolo --in {workdir} -s {skill}` (also process cwd; do not pass Hermes `-w`/`--worktree`) |
| opencode | `opencode` | `run --auto {prompt}` (workdir via process cwd; no `--dir` on local v2.x) |
| opencode-qwen38-max | `opencode` | `run --auto --model opencode-go/qwen3.8-max {prompt}` ([OpenCode Go](https://opencode.ai/docs/go/)) |
| opencode-deepseek-v41-flash | `opencode` | `run --auto --model opencode-go/deepseek-v4.1-flash {prompt}` |

Hermes: project skills under `.hermes/skills/` and `.agents/skills/` are trust-gated. Before every Hermes agent run, agent-orc runs `hermes skills trust` on the worktree and the target `--repo-root` (failures are logged; the run continues). agent-orc does not bind or delete Hermes sessions for `-z` oneshots.

OpenCode providers: agent-orc injects `--session <id>` when missing, then runs `opencode session delete <id>` when the run ends or on forced shutdown (before process kill — kill alone is not enough; the OpenCode server can respawn killed sessions).

Example agent→provider mapping: planner → `opencode-qwen38-max`; refine → `grok`; verify → `opencode-deepseek-v41-flash`; others → `cursor`.

## Schedules

Optional top-level `schedules:` map. Each entry has:

| Key | Meaning |
|-----|---------|
| `cron` | 5-field cron (`minute hour dom month dow`), evaluated in the **host local timezone** |
| `agents` | Non-empty list of agent names defined under `agents:` |

Any agent named in at least one schedule is **schedule-only**: it does not run a cooldown loop. The supervisor polls about every `schedule_poll_seconds`; when the current minute matches the cron and that minute has not already been consumed, it attempts **one** run (or one chain pass). Gates, issues, and `parallel_run` still apply. A gate/claim miss consumes the tick and waits for the next cron match (no gate backoff spin). If a run overruns into later matching minutes, those ticks are skipped (no catch-up). The same agent may appear in multiple schedules (separate loops). `-n N` means N successful fires per schedule slot.

Example (shipped sample):

```yaml
schedules:
  hourly-planner:
    cron: "0 * * * *"
    agents:
      - project-planner-agent
```

## Agents

Two shapes under `agents:`:

1. **Leaf** — `skill`, `provider`, `enabled`, `prompt`, optional `gate.command`, optional `parallel_run`, optional `issues.command`, and optional timing.
2. **Composite (chain)** — `enabled`, non-empty `chain:`, optional `gate.command`, optional `parallel_run`, and optional timing. Must **not** set `skill`, `provider`, `prompt`, or `issues`.

Each timing key falls back to the orchestrator value on its own:

| Key | Fallback |
|-----|----------|
| `cooldown_seconds` | `orchestrator.cooldown_seconds` |
| `gate_backoff_initial_seconds` | `orchestrator.gate_backoff_initial_seconds` |
| `gate_backoff_max_seconds` | `orchestrator.gate_backoff_max_seconds` |

Values are numbers `>= 0`. Setting one key does not change the others.

**Skills:** `skill` names must resolve in the **target project** (typically `.agents/skills/<skill>/` with native facades). agent-orc does not ship those skills.

**Gate:** exit code **0** = pass (run agent); non-zero = miss. Omit `gate` → always pass. Stdout ignored. Composites and leaf steps may each have a gate (see chains below).

**parallel_run:** integer **>= 1**. Omitted means **1** (one loop, no issue claim on leaves). Above 1, that many slots run. Each slot keeps its own cooldown and gate backoff. `-n` counts per slot (one full chain pass for composites).

**issues.command:** optional on **leaves** (and chain steps). Prints a JSON array of objects with `number`, the same shape as `gh issue list --json number`. For standalone leaves, used only when `parallel_run` > 1. After the gate passes, the slot claims the **first free number in that list order** that no slot in this process owns. No free number is a claim miss: same backoff as a gate miss, no worktree, and it does not count toward `-n`. The map lives in memory for this process only. Prompt placeholders `{parallel_id}` and `{issue}` are always filled (`issue` is `none` when nothing was claimed).

### Chains (composites)

A composite is a selectable agent that runs an ordered list of **leaf** steps in one slot. It can run side by side with other leaves or composites.

`chain` entries are either:

- a **name ref** to an existing leaf under `agents:` (copies that leaf’s skill/provider/prompt/gate/issues/timing into a separate step instance), or
- an **inline** leaf mapping (`skill`, `provider`, `prompt`, optional gate/issues/timing). Inline steps must not set `enabled`, `parallel_run`, or `chain`.

Named leaves may also run standalone. The same leaf listed alone and inside a chain yields **separate instances** (no shared runtime). Leaf `enabled` only affects standalone selection; refs still resolve when the leaf is disabled. Nested chains (ref to another composite) are rejected.

Per composite slot iteration:

1. Composite gate — miss → backoff (does not count toward `-n`).
2. For each step in order: step gate miss or issue claim miss → **skip** that step and continue; otherwise new worktree → run → cleanup. Step failure keeps going. After a step that ran, apply that step’s cooldown.
3. After all steps: apply the composite’s cooldown, then count **one** `-n` pass (even if every step was skipped or failed).

Composites must not set `issues` at the chain level; only steps claim issues. When a step has `issues`, it claims whenever present (including inside a `parallel_run: 1` composite).

Example:

```yaml
agents:
  issue-workflow-review-agent:
    skill: issue-workflow-review-agent
    provider: cursor
    enabled: true
    prompt: |
      ...
  review-then-refine:
    enabled: true
    cooldown_seconds: 60
    chain:
      - issue-workflow-review-agent
      - skill: issue-workflow-refine-agent
        provider: grok
        prompt: |
          Run refine unattended.
```

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
