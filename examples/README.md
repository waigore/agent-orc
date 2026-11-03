# Examples for target projects

Copy these into a **project** repository. agent-orc does not read this directory at runtime.

| Path | Copy to (in the project) |
|------|--------------------------|
| [`config.yaml`](config.yaml) | `.orc/config.yaml` |
| [`config.local.example.yaml`](config.local.example.yaml) | start of `.orc/config.local.yaml` (optional) |
| [`scripts/`](scripts/) | `.orc/scripts/` |

Then ensure every `skill:` named in the config exists under the project’s `.agents/skills/` (with native facades). See [`docs/project-integration.md`](../docs/project-integration.md).

```bash
agent-orc --repo-root /path/to/project --yes -n 1
```
