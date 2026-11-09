# agent-orc architecture

## Role

agent-orc is an **independent orchestrator**: install once, point at any git repo with `.orc/config.*.yaml` and project-local skills. It does not embed or execute against its own skill catalog.

## Layers

1. **CLI** (`cli.py`): argparse, `--repo-root` / `--config-dir`, config load, multi-select, asyncio entry.
2. **Supervisor** (`supervisor.py`): one asyncio task per parallel slot; stagger, gate, optional issue claim, pull, worktree, run, cooldown; cron schedule loops for agents listed under `schedules:`.
3. **Schedule** (`schedule.py`): cron match helpers in `orchestrator.timezone` (default `Asia/Hong_Kong`) for schedule-only slots.
4. **Gate** (`gate.py`): optional subprocess; exit 0 to proceed (cwd = target repo root).
5. **Assignment** (`assignment.py`): `{parallel_id}` / `{issue}` in the prompt, and the in-memory issue map.
6. **Worktree** (`worktree.py`): create/delete isolated checkouts under the target repo; pull on orchestrator root.
7. **Crew bridge** (`crew/`): CrewAI Agent/Task/Crew + `ProviderCliTool`; default path invokes the tool directly (no LLM) so CLI cost is the agent run itself. Optional `use_crew_kickoff` for future LLM-driven use.
8. **Providers** (`providers/`): render configured argv templates.
9. **Messaging** (`messaging.py`): no-op `publish` / `subscribe` for later agent-to-agent hooks.
10. **Shutdown** (`shutdown.py`): SIGINT confirm, delete tracked OpenCode sessions, kill process groups, purge worktrees.
11. **github_gh** (`github_gh.py`): thin `gh` wrapper for e2e (not used by the daemon loop).

## Parallelism

Selected agents (leaves and composites) run concurrently. Agents named under `schedules:` get schedule loops instead of cooldown loops; other selected agents keep recurring loops. Each agent starts `parallel_run` loops (default **1**). Loops are staggered. Within one **leaf** loop: at most one agent process. Gate misses never start a worktree or CLI.

A **composite** slot runs its `chain` steps **sequentially** in that same slot (each step gets its own worktree). Other selected agents still run in parallel with that composite slot.

When a leaf has `parallel_run` greater than 1 and `issues.command` is set, a loop claims the first free issue in the command's list order after the gate passes. Chain steps claim whenever they have `issues` (even under a `parallel_run: 1` composite); a step claim miss skips that step and continues. One in-memory map covers the whole daemon, so an issue has at most one owner. The map is not saved. A leaf claim miss uses the same backoff as a gate miss and does not count toward `-n`. Ownership is released when that run ends, including failure. A new process starts with an empty map.

`{parallel_id}` (stable slot number, from 1) and `{issue}` (`none` when unassigned) are filled in that run's prompt. Without `issues.command`, extra slots still run, with ids only. Cooldown and gate backoff apply separately to each slot.

## Extensibility

- New provider: add template under `providers:` in the **project** config (and optional module stub here).
- New skill agent: add under `agents:` in the project config; the skill body must exist in that project.
- Future bus: replace no-ops in `messaging.py`; supervisor already publishes `skill.start` / `skill.end`.
