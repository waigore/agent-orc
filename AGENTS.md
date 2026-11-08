# AGENTS.md

Agent entrypoint for this repo. Keep this file short; put detail in `docs/` and `.agents/`.

## Project

- **Purpose**: Independent skill-agent orchestrator — point at a local project repo and run agents from that project’s `.orc/config.*.yaml` and `.agents/skills/`.
- **Language / runtime**: Python 3.11+
- **Frameworks / tools**: uv, CrewAI bridge, PyYAML, questionary; provider CLIs (cursor-agent, grok, hermes, opencode)

## Quick start commands

- **Setup**: `uv sync --group dev`
- **Run** (against a **target** project, not this checkout’s tree): `uv run agent-orc --repo-root /path/to/project --yes -n 1`
- **Test**: `uv run pytest -m "not e2e"`
- **Build / install**: `uv sync` / editable install; console script `agent-orc`

## Skills

Canonical skills and catalog: [`.agents/`](.agents/) ([README](.agents/README.md)). Authoring and native facades: [`docs/skills.md`](docs/skills.md).

This repo keeps a **minimal** skill set for developing agent-orc. Workflow skills that agents execute live in the **target project** (e.g. game-dev-template).

## Key files and directories

- `AGENTS.md` — this file (agent orientation)
- [`.agents/`](.agents/) — ([README](.agents/README.md))
- [`.cursor/`](.cursor/) — ([README](.cursor/README.md))
- [`.opencode/`](.opencode/) — ([README](.opencode/README.md))
- [`.grok/`](.grok/) — ([README](.grok/README.md))
- [`.hermes/`](.hermes/) — ([README](.hermes/README.md))
- [`src/agent_orc/`](src/agent_orc/) — package source
- [`docs/`](docs/) — usage, config, architecture, project integration
- [`examples/`](examples/) — sample `.orc` config + scripts for **projects** (not used by this package at runtime)
- [`tests/`](tests/) — unit / integration / e2e

## Rules to live by

**Before any work, read [`.agents/rules.md`](.agents/rules.md).**

- **Target project owns skills and config**: never invent a parallel skill catalog here for production runs; agents resolve skills from `--repo-root`.
- **No `.orc/` in this repo**: runtime config is always under the target project; ship samples only under `examples/`.
- **Small PRs only**: `main` is protected; land via PR ([`docs/pull-requests.md`](docs/pull-requests.md)). Run `uv run ruff check .` and `uv run pytest -m "not e2e"` before claiming green.
- **Docs match CLI**: when changing flags or config merge behavior, update `docs/usage.md` and `docs/config.md` in the same change.
- **Facades stay thin**: edit skill bodies only under `.agents/skills/`; keep Cursor/OpenCode/Grok/Hermes facades as pointers ([`docs/skills.md`](docs/skills.md)).
