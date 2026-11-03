"""Agent multi-select at startup."""

from __future__ import annotations

from agent_orc.config import AgentConfig, AppConfig, ConfigError, enabled_agents


def resolve_selected_agents(
    config: AppConfig,
    *,
    yes: bool = False,
    agents_csv: str | None = None,
    interactive: bool = True,
) -> list[AgentConfig]:
    available = enabled_agents(config)
    if not available:
        raise ConfigError("no enabled agents in config")

    if agents_csv:
        names = [n.strip() for n in agents_csv.split(",") if n.strip()]
        selected: list[AgentConfig] = []
        for name in names:
            agent = config.agents.get(name)
            if agent is None:
                raise ConfigError(f"unknown agent: {name}")
            if not agent.enabled:
                raise ConfigError(f"agent is disabled: {name}")
            selected.append(agent)
        return selected

    if yes or not interactive:
        return list(available)

    return _interactive_select(available)


def _interactive_select(available: list[AgentConfig]) -> list[AgentConfig]:
    import questionary

    choices = [questionary.Choice(title=a.name, value=a.name, checked=True) for a in available]
    names = questionary.checkbox(
        "Select agents to spin up:",
        choices=choices,
    ).ask()
    if names is None:
        raise ConfigError("selection cancelled")
    if not names:
        raise ConfigError("no agents selected")
    by_name = {a.name: a for a in available}
    return [by_name[n] for n in names]
