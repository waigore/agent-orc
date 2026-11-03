# Secondary rules

Top five rules live in [`AGENTS.md`](../AGENTS.md). Additional guidance:

- Prefer extending existing modules under `src/agent_orc/` over new parallel packages.
- Config merge and env expansion are defined in `config.py` + [`docs/config.md`](../docs/config.md); do not invent a second merge path.
- E2e tests hit real GitHub and provider CLIs — never run them unprompted.
- Samples under `examples/` are for projects to copy; do not load them as this package’s runtime config.
