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


def _parse_agents(raw: dict[str, Any], providers: dict[str, list[str]]) -> dict[str, AgentConfig]:
    agents: dict[str, AgentConfig] = {}
    for name, body in raw.items():
        if not isinstance(body, dict):
            raise ConfigError(f"agents.{name} must be a mapping")
        provider = str(body.get("provider", ""))
        if provider not in providers:
            raise ConfigError(f"agents.{name}.provider '{provider}' is not defined under providers")
        gate = None
        gate_raw = body.get("gate")
        if gate_raw is not None:
            if not isinstance(gate_raw, dict) or "command" not in gate_raw:
                raise ConfigError(f"agents.{name}.gate must have a command")
            gate = GateConfig(
                command=_as_command(gate_raw["command"], f"agents.{name}.gate.command")
            )
        issues = None
        issues_raw = body.get("issues")
        if issues_raw is not None:
            if not isinstance(issues_raw, dict) or "command" not in issues_raw:
                raise ConfigError(f"agents.{name}.issues must have a command")
            issues = IssuesConfig(
                command=_as_command(issues_raw["command"], f"agents.{name}.issues.command")
            )
        agents[name] = AgentConfig(
            name=name,
            skill=str(body.get("skill", name)),
            provider=provider,
            enabled=bool(body.get("enabled", True)),
            prompt=str(body.get("prompt", "")).strip(),
            gate=gate,
            issues=issues,
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
        )
        if not agents[name].prompt:
            raise ConfigError(f"agents.{name}.prompt is required")
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
