# Project integration

How a software/game (or other) repo uses agent-orc. Skill bodies, issue workflow, and labels live in the **project** (e.g. [game-dev-template](https://github.com/waigore/game-dev-template)); this package only schedules provider CLIs against that tree.

## Layout in the project

```
my-project/
  .orc/
    config.yaml              # from examples/config.yaml (adapted)
    config.local.yaml        # optional overrides (gitignored)
    scripts/                 # optional; from examples/scripts/
    logs/                    # runtime
    worktrees/               # runtime
  .agents/skills/<skill>/    # required: skills named in config
  .cursor/skills/…           # thin facades (project convention)
  .grok/skills/…
  .opencode/skill/…
```

Wire agent-orc:

```bash
agent-orc --repo-root /path/to/my-project --yes
```

## Assigned issue contract

Background dispatch agents typically receive a prompt line like `Assigned issue: N` or `Assigned issue: none`:

- A numeric `N` means treat that as `#n` for the underlying project skill.
- `none` means the orchestrator did not claim an issue; the agent discovers one candidate using the project’s rules (status labels, priority, judgement).

Orchestrator `issues.command` (when `parallel_run` > 1) is only a **parallel lock** over a pre-ordered list. Discovery with `none` still applies project judgement. Example list scripts: [`examples/scripts/`](../examples/scripts/).

## Skills and facades

Canonical skills live under the project’s `.agents/skills/`. Cursor / Grok / OpenCode use thin facades that point at those bodies — see [skills.md](skills.md). agent-orc prompts name a skill; the provider agent must resolve it from the **worktree** (a checkout of the project), not from the agent-orc package.

## Sample agents

[`examples/config.yaml`](../examples/config.yaml) mirrors a typical template crew (planner, issue-workflow-*, feedback, babysit-pr). Those skill names must exist in the target project or you must edit the config. Disable or remap agents in `config.local.yaml`.
