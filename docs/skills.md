# Skills (this repo)

Canonical skill bodies for **developing agent-orc** live under [`.agents/skills/`](../.agents/skills/) (one folder per skill). That tree is the only source of truth in this repository.

Project workflow skills (issue agents, planner, etc.) live in the **target project** (e.g. game-dev-template), not here. See [project-integration.md](project-integration.md).

## Native wiring (required)

Whenever a skill is created or renamed in this repo, add thin facades for OpenCode, Cursor, Grok, and Hermes. Facades carry the same `name` / `description` frontmatter and point at the canonical body — they must not duplicate the workflow.

| Agent | Facade path |
|-------|-------------|
| Cursor | `.cursor/skills/<skill-name>/SKILL.md` |
| OpenCode | `.opencode/skill/<skill-name>/SKILL.md` |
| Grok | `.grok/skills/<skill-name>/SKILL.md` |
| Hermes | `.hermes/skills/<skill-name>/SKILL.md` |

### Facade template

```markdown
---
name: <skill-name>
description: |-
  <same description as the canonical skill>
---

# <Title> (facade)

Canonical instructions: [`.agents/skills/<skill-name>/SKILL.md`](../../../.agents/skills/<skill-name>/SKILL.md).

Read that file and its `references/` as needed, then run the workflow there. Do not invent a parallel process.
```

### Rules

- Edit the body only under `.agents/skills/<skill-name>/`.
- Keep facade frontmatter in sync when you change the canonical `name` or `description`.
- Do not replace a facade with a full copy of the skill.
- Do not use directory-wide symlinks for Cursor/OpenCode/Grok/Hermes in this repo; use per-skill facades so each agent’s native path stays explicit.

## Add a skill checklist

1. Create `.agents/skills/<skill-name>/SKILL.md` (`name` must match the folder).
2. Add optional `scripts/`, `references/`, or `assets/` next to that `SKILL.md`.
3. Add Cursor, OpenCode, Grok, and Hermes facades using the template above.
4. List the skill in [`.agents/skills/README.md`](../.agents/skills/README.md). Do not maintain a full skill list in `AGENTS.md`.
