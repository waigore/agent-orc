# agent-orc

Independent daemon that runs configured skill agents (Cursor / Grok / OpenCode) in isolated git worktrees of a **target project**.

agent-orc does not own project skills or workflow. Point it at a repo that has `.orc/config.yaml` (and skills under that repo’s `.agents/`). Sample config for projects: [`examples/`](examples/).

## Quick start

```bash
# From this checkout
uv sync --group dev
uv run agent-orc --repo-root /path/to/project --yes -n 1

# Or install editable / as a tool, then
agent-orc --repo-root /path/to/project --yes -n 1
```

Config is always read from the **target** project: `<repo>/.orc/config.yaml` plus optional `config.local.yaml`. This package has no `.orc/` of its own and will not run against configs in its install tree.

Docs: [usage](docs/usage.md) · [config](docs/config.md) · [architecture](docs/architecture.md) · [project integration](docs/project-integration.md)

## Tests

```bash
uv run pytest -m "not e2e"
uv run pytest -m "not e2e" && uv run pytest -m e2e   # e2e last; needs gh + real CLIs
```
