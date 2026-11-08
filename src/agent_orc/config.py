"""Load and deep-merge .orc/config.yaml + config.local.yaml."""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class ConfigError(Exception):
    """Invalid or incomplete orchestrator configuration."""


_ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge override into base; override wins on leaf conflicts."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _expand_env_string(value: str) -> str:
    """Expand ${VAR} and ${VAR:-default} in a string; fail fast if VAR is unset."""

    def repl(match: re.Match[str]) -> str:
        expr = match.group(1)
        if ":-" in expr:
            name, default = expr.split(":-", 1)
            return os.environ.get(name, default)
        if expr not in os.environ:
            raise ConfigError(f"Unset environment variable: {expr}")
        return os.environ[expr]

    return _ENV_PATTERN.sub(repl, value)


def expand_env_in_tree(node: Any) -> Any:
    """Recursively expand env placeholders in all string leaves."""
    if isinstance(node, dict):
        return {k: expand_env_in_tree(v) for k, v in node.items()}
    if isinstance(node, list):
        return [expand_env_in_tree(v) for v in node]
    if isinstance(node, str):
        return _expand_env_string(node)
    return node


@dataclass
class GateConfig:
    command: list[str]


@dataclass
class IssuesConfig:
    command: list[str]


@dataclass
class AgentConfig:
    name: str
    skill: str
    provider: str
    enabled: bool
    prompt: str
    gate: GateConfig | None = None
    issues: IssuesConfig | None = None
    parallel_run: int = 1
    cooldown_seconds: float | None = None
    gate_backoff_initial_seconds: float | None = None
    gate_backoff_max_seconds: float | None = None
    chain: list[AgentConfig] | None = None


def is_composite(agent: AgentConfig) -> bool:
    return agent.chain is not None


@dataclass
class OrchestratorConfig:
    cooldown_seconds: float = 10.0
    gate_backoff_initial_seconds: float = 10.0
    gate_backoff_max_seconds: float = 60.0
    stagger_seconds: float = 5.0
    worktrees_dir: str = ".orc/worktrees"
    logs_dir: str = ".orc/logs"
    repo_root: str = "."
    pull_before_run: bool = True
    default_branch: str = "main"


@dataclass
class AppConfig:
    orchestrator: OrchestratorConfig
    providers: dict[str, list[str]]
    agents: dict[str, AgentConfig]
    config_dir: Path = field(default_factory=lambda: Path(".orc"))


def _as_command(value: Any, label: str) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(x, (str, int, float)) for x in value):
        return [str(x) for x in value]
    raise ConfigError(f"{label} must be a string or list of strings")


def _non_negative_seconds(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{label} must be a number >= 0")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ConfigError(f"{label} must be a number >= 0")
    return number


def _parallel_run(body: dict[str, Any], name: str) -> int:
    label = f"agents.{name}.parallel_run"
    if "parallel_run" not in body or body["parallel_run"] is None:
        return 1
    value = body["parallel_run"]
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ConfigError(f"{label} must be an integer >= 1")
    return value


def _optional_seconds(body: dict[str, Any], key: str, label: str) -> float | None:
    if key not in body or body[key] is None:
        return None
    return _non_negative_seconds(body[key], label)


def resolved_cooldown_seconds(agent: AgentConfig, orch: OrchestratorConfig) -> float:
    if agent.cooldown_seconds is None:
        return orch.cooldown_seconds
    return agent.cooldown_seconds


def resolved_gate_backoff_initial_seconds(agent: AgentConfig, orch: OrchestratorConfig) -> float:
    if agent.gate_backoff_initial_seconds is None:
        return orch.gate_backoff_initial_seconds
    return agent.gate_backoff_initial_seconds


def resolved_gate_backoff_max_seconds(agent: AgentConfig, orch: OrchestratorConfig) -> float:
    if agent.gate_backoff_max_seconds is None:
        return orch.gate_backoff_max_seconds
    return agent.gate_backoff_max_seconds


def _parse_orchestrator(raw: dict[str, Any]) -> OrchestratorConfig:
    cooldown = _non_negative_seconds(
        raw.get("cooldown_seconds", 10), "orchestrator.cooldown_seconds"
    )
    if "gate_backoff_initial_seconds" in raw and raw["gate_backoff_initial_seconds"] is not None:
        gate_initial = _non_negative_seconds(
            raw["gate_backoff_initial_seconds"],
            "orchestrator.gate_backoff_initial_seconds",
        )
    else:
        gate_initial = cooldown
    return OrchestratorConfig(
        cooldown_seconds=cooldown,
        gate_backoff_initial_seconds=gate_initial,
        gate_backoff_max_seconds=_non_negative_seconds(
            raw.get("gate_backoff_max_seconds", 60),
            "orchestrator.gate_backoff_max_seconds",
        ),
        stagger_seconds=float(raw.get("stagger_seconds", 5)),
        worktrees_dir=str(raw.get("worktrees_dir", ".orc/worktrees")),
        logs_dir=str(raw.get("logs_dir", ".orc/logs")),
        repo_root=str(raw.get("repo_root", ".")),
        pull_before_run=bool(raw.get("pull_before_run", True)),
        default_branch=str(raw.get("default_branch", "main")),
    )


def _parse_providers(raw: dict[str, Any]) -> dict[str, list[str]]:
    providers: dict[str, list[str]] = {}
    for name, body in raw.items():
        if not isinstance(body, dict) or "command" not in body:
            raise ConfigError(f"providers.{name} must have a command")
        providers[name] = _as_command(body["command"], f"providers.{name}.command")
    return providers


def _parse_gate(raw: Any, label: str) -> GateConfig:
    if not isinstance(raw, dict) or "command" not in raw:
        raise ConfigError(f"{label} must have a command")
    return GateConfig(command=_as_command(raw["command"], f"{label}.command"))


def _parse_issues(raw: Any, label: str) -> IssuesConfig:
    if not isinstance(raw, dict) or "command" not in raw:
        raise ConfigError(f"{label} must have a command")
    return IssuesConfig(command=_as_command(raw["command"], f"{label}.command"))


def _parse_leaf_agent(
    name: str,
    body: dict[str, Any],
    providers: dict[str, list[str]],
    *,
    label: str | None = None,
) -> AgentConfig:
    """Parse a leaf agent (standalone or inline chain step)."""
    path = label or f"agents.{name}"
    if "chain" in body and body["chain"] is not None:
        raise ConfigError(f"{path} must not set chain (nested chains are forbidden)")
    provider = str(body.get("provider", ""))
    if provider not in providers:
        raise ConfigError(f"{path}.provider '{provider}' is not defined under providers")
    gate = None
    if body.get("gate") is not None:
        gate = _parse_gate(body["gate"], f"{path}.gate")
    issues = None
    if body.get("issues") is not None:
        issues = _parse_issues(body["issues"], f"{path}.issues")
    prompt = str(body.get("prompt", "")).strip()
    if not prompt:
        raise ConfigError(f"{path}.prompt is required")
    return AgentConfig(
        name=name,
        skill=str(body.get("skill", name)),
        provider=provider,
        enabled=bool(body.get("enabled", True)),
        prompt=prompt,
        gate=gate,
        issues=issues,
        parallel_run=_parallel_run(body, name) if label is None else 1,
        cooldown_seconds=_optional_seconds(body, "cooldown_seconds", f"{path}.cooldown_seconds"),
        gate_backoff_initial_seconds=_optional_seconds(
            body,
            "gate_backoff_initial_seconds",
            f"{path}.gate_backoff_initial_seconds",
        ),
        gate_backoff_max_seconds=_optional_seconds(
            body,
            "gate_backoff_max_seconds",
            f"{path}.gate_backoff_max_seconds",
        ),
        chain=None,
    )


def _copy_leaf_as_step(composite_name: str, ref: str, leaf: AgentConfig) -> AgentConfig:
    if leaf.chain is not None:
        raise ConfigError(
            f"agents.{composite_name}.chain ref '{ref}' must be a leaf agent "
            "(nested chains are forbidden)"
        )
    return AgentConfig(
        name=f"{composite_name}:{ref}",
        skill=leaf.skill,
        provider=leaf.provider,
        enabled=True,
        prompt=leaf.prompt,
        gate=leaf.gate,
        issues=leaf.issues,
        parallel_run=1,
        cooldown_seconds=leaf.cooldown_seconds,
        gate_backoff_initial_seconds=leaf.gate_backoff_initial_seconds,
        gate_backoff_max_seconds=leaf.gate_backoff_max_seconds,
        chain=None,
    )


def _parse_chain_step(
    composite_name: str,
    index: int,
    entry: Any,
    providers: dict[str, list[str]],
    leaves: dict[str, AgentConfig],
) -> AgentConfig:
    label = f"agents.{composite_name}.chain[{index}]"
    if isinstance(entry, str):
        ref = entry
        if ref not in leaves:
            raise ConfigError(f"{label} ref '{ref}' is unknown or not a leaf agent")
        return _copy_leaf_as_step(composite_name, ref, leaves[ref])
    if not isinstance(entry, dict):
        raise ConfigError(f"{label} must be a leaf agent name or a mapping")
    for forbidden in ("enabled", "parallel_run", "chain"):
        if forbidden in entry:
            raise ConfigError(f"{label} must not set {forbidden}")
    step_name = f"{composite_name}:step-{index + 1}"
    return _parse_leaf_agent(step_name, entry, providers, label=label)


def _parse_composite_agent(
    name: str,
    body: dict[str, Any],
    providers: dict[str, list[str]],
    leaves: dict[str, AgentConfig],
) -> AgentConfig:
    for forbidden in ("skill", "provider", "prompt", "issues"):
        if forbidden in body:
            raise ConfigError(
                f"agents.{name} is a chain composite and must not set {forbidden}"
            )
    chain_raw = body.get("chain")
    if not isinstance(chain_raw, list) or len(chain_raw) == 0:
        raise ConfigError(f"agents.{name}.chain must be a non-empty list")
    gate = None
    if body.get("gate") is not None:
        gate = _parse_gate(body["gate"], f"agents.{name}.gate")
    steps = [
        _parse_chain_step(name, index, entry, providers, leaves)
        for index, entry in enumerate(chain_raw)
    ]
    return AgentConfig(
        name=name,
        skill="",
        provider="",
        enabled=bool(body.get("enabled", True)),
        prompt="",
        gate=gate,
        issues=None,
        parallel_run=_parallel_run(body, name),
        cooldown_seconds=_optional_seconds(
            body, "cooldown_seconds", f"agents.{name}.cooldown_seconds"
        ),
        gate_backoff_initial_seconds=_optional_seconds(
            body,
            "gate_backoff_initial_seconds",
            f"agents.{name}.gate_backoff_initial_seconds",
        ),
        gate_backoff_max_seconds=_optional_seconds(
            body,
            "gate_backoff_max_seconds",
            f"agents.{name}.gate_backoff_max_seconds",
        ),
        chain=steps,
    )


def _parse_agents(raw: dict[str, Any], providers: dict[str, list[str]]) -> dict[str, AgentConfig]:
    leaves_raw: dict[str, dict[str, Any]] = {}
    composites_raw: dict[str, dict[str, Any]] = {}
    for name, body in raw.items():
        if not isinstance(body, dict):
            raise ConfigError(f"agents.{name} must be a mapping")
        if "chain" in body and body["chain"] is not None:
            composites_raw[name] = body
        else:
            leaves_raw[name] = body

    leaves: dict[str, AgentConfig] = {}
    for name, body in leaves_raw.items():
        leaves[name] = _parse_leaf_agent(name, body, providers)

    agents: dict[str, AgentConfig] = dict(leaves)
    for name, body in composites_raw.items():
        agents[name] = _parse_composite_agent(name, body, providers, leaves)
    return agents


def load_config(config_dir: Path | None = None) -> AppConfig:
    """Load config.yaml and optional config.local.yaml from config_dir."""
    root = Path(config_dir) if config_dir is not None else Path(".orc")
    base_path = root / "config.yaml"
    if not base_path.is_file():
        raise ConfigError(f"Missing config file: {base_path}")

    with base_path.open(encoding="utf-8") as fh:
        base = yaml.safe_load(fh) or {}
    if not isinstance(base, dict):
        raise ConfigError("config.yaml must be a mapping")

    local_path = root / "config.local.yaml"
    if local_path.is_file():
        with local_path.open(encoding="utf-8") as fh:
            local = yaml.safe_load(fh) or {}
        if not isinstance(local, dict):
            raise ConfigError("config.local.yaml must be a mapping")
        merged = deep_merge(base, local)
    else:
        merged = base

    merged = expand_env_in_tree(merged)

    orch_raw = merged.get("orchestrator") or {}
    if not isinstance(orch_raw, dict):
        raise ConfigError("orchestrator must be a mapping")
    providers_raw = merged.get("providers") or {}
    if not isinstance(providers_raw, dict):
        raise ConfigError("providers must be a mapping")
    agents_raw = merged.get("agents") or {}
    if not isinstance(agents_raw, dict):
        raise ConfigError("agents must be a mapping")

    providers = _parse_providers(providers_raw)
    agents = _parse_agents(agents_raw, providers)
    return AppConfig(
        orchestrator=_parse_orchestrator(orch_raw),
        providers=providers,
        agents=agents,
        config_dir=root.resolve(),
    )


def enabled_agents(config: AppConfig) -> list[AgentConfig]:
    return [a for a in config.agents.values() if a.enabled]
