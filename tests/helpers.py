from __future__ import annotations

from pathlib import Path

import yaml


def write_test_config(
    config_dir: Path,
    *,
    fake_cli: Path,
    agents: list[str] | None = None,
    cooldown: float = 0,
    stagger: float = 0,
    gate_initial: float | None = None,
    gate_max: float = 60,
    pull_before_run: bool = False,
    gates: dict[str, list[str]] | None = None,
    agent_timing: dict[str, dict] | None = None,
) -> Path:
    config_dir.mkdir(parents=True, exist_ok=True)
    names = agents or [
        "project-planner-agent",
        "issue-workflow-review-agent",
    ]
    agent_map = {}
    for name in names:
        entry: dict = {
            "skill": name,
            "provider": "fake",
            "enabled": True,
            "prompt": f"run {name}",
        }
        if gates and name in gates:
            entry["gate"] = {"command": gates[name]}
        if agent_timing and name in agent_timing:
            entry.update(agent_timing[name])
        agent_map[name] = entry

    orchestrator = {
        "cooldown_seconds": cooldown,
        "gate_backoff_max_seconds": gate_max,
        "stagger_seconds": stagger,
        "worktrees_dir": ".orc/worktrees",
        "logs_dir": ".orc/logs",
        "repo_root": ".",
        "pull_before_run": pull_before_run,
        "default_branch": "main",
    }
    if gate_initial is not None:
        orchestrator["gate_backoff_initial_seconds"] = gate_initial

    data = {
        "orchestrator": orchestrator,
        "providers": {
            "fake": {
                "command": [
                    "python3",
                    str(fake_cli),
                    "{skill}",
                ]
            }
        },
        "agents": agent_map,
    }
    path = config_dir / "config.yaml"
    path.write_text(yaml.dump(data), encoding="utf-8")
    return path
