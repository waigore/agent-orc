from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from agent_orc.config import (
    ConfigError,
    deep_merge,
    enabled_agents,
    expand_env_in_tree,
    is_composite,
    load_config,
    resolved_cooldown_seconds,
    resolved_gate_backoff_initial_seconds,
    resolved_gate_backoff_max_seconds,
)


def test_deep_merge_nested() -> None:
    base = {"a": {"x": 1, "y": 2}, "b": 3}
    override = {"a": {"y": 9}, "c": 4}
    assert deep_merge(base, override) == {"a": {"x": 1, "y": 9}, "b": 3, "c": 4}


def test_load_defaults_and_local(tmp_path: Path) -> None:
    cfg_dir = tmp_path / ".orc"
    cfg_dir.mkdir()
    (cfg_dir / "config.yaml").write_text(
        yaml.dump(
            {
                "orchestrator": {"cooldown_seconds": 10},
                "providers": {"cursor": {"command": ["agent"]}},
                "agents": {
                    "a": {
                        "skill": "a",
                        "provider": "cursor",
                        "enabled": True,
                        "prompt": "go",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (cfg_dir / "config.local.yaml").write_text(
        yaml.dump(
            {
                "orchestrator": {"cooldown_seconds": 3},
                "agents": {"a": {"enabled": False}},
            }
        ),
        encoding="utf-8",
    )
    cfg = load_config(cfg_dir)
    assert cfg.orchestrator.cooldown_seconds == 3
    assert enabled_agents(cfg) == []


def test_missing_local_ok(tmp_path: Path) -> None:
    cfg_dir = tmp_path / ".orc"
    cfg_dir.mkdir()
    (cfg_dir / "config.yaml").write_text(
        yaml.dump(
            {
                "providers": {"p": {"command": ["echo"]}},
                "agents": {
                    "a": {
                        "skill": "a",
                        "provider": "p",
                        "enabled": True,
                        "prompt": "x",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    cfg = load_config(cfg_dir)
    assert "a" in cfg.agents


def test_invalid_provider_ref(tmp_path: Path) -> None:
    cfg_dir = tmp_path / ".orc"
    cfg_dir.mkdir()
    (cfg_dir / "config.yaml").write_text(
        yaml.dump(
            {
                "providers": {"p": {"command": ["echo"]}},
                "agents": {
                    "a": {
                        "skill": "a",
                        "provider": "missing",
                        "enabled": True,
                        "prompt": "x",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="not defined"):
        load_config(cfg_dir)


def test_shipped_config_loads() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = load_config(root / "examples")
    assert "project-planner-agent" in cfg.agents
    planner = cfg.agents["project-planner-agent"]
    assert planner.gate is None
    assert planner.provider == "opencode-qwen38-max"
    assert planner.cooldown_seconds is None
    assert resolved_cooldown_seconds(planner, cfg.orchestrator) == 10
    assert planner.gate_backoff_initial_seconds is None
    assert resolved_gate_backoff_initial_seconds(planner, cfg.orchestrator) == 10
    assert "opencode-go/qwen3.8-max" in cfg.providers["opencode-qwen38-max"]
    assert cfg.agents["issue-workflow-refine-agent"].provider == "grok"
    assert cfg.agents["issue-workflow-verify-agent"].provider == "opencode-deepseek-v41-flash"
    assert "opencode-go/deepseek-v4.1-flash" in cfg.providers["opencode-deepseek-v41-flash"]
    assert cfg.agents["issue-workflow-review-agent"].gate is not None
    assert cfg.orchestrator.cooldown_seconds == 10
    assert cfg.orchestrator.gate_backoff_initial_seconds == 10
    assert cfg.orchestrator.gate_backoff_max_seconds == 60
    assert cfg.orchestrator.schedule_poll_seconds == 5
    assert "hourly-planner" in cfg.schedules
    hourly = cfg.schedules["hourly-planner"]
    assert hourly.cron == "0 * * * *"
    assert hourly.agents == ["project-planner-agent"]
    implement = cfg.agents["issue-workflow-implement-agent"]
    assert implement.cooldown_seconds is None
    assert resolved_cooldown_seconds(implement, cfg.orchestrator) == 10
    assert resolved_gate_backoff_initial_seconds(implement, cfg.orchestrator) == 10
    assert resolved_gate_backoff_max_seconds(implement, cfg.orchestrator) == 60
    babysit = cfg.agents["babysit-pr-agent"]
    assert babysit.provider == "cursor"
    assert babysit.gate is not None
    assert babysit.gate.command[-1].endswith("babysit-pr-agent/scripts/gate.sh")
    assert len(enabled_agents(cfg)) == 9
    chain = cfg.agents["review-then-refine"]
    assert is_composite(chain)
    assert chain.chain is not None
    assert [s.skill for s in chain.chain] == [
        "issue-workflow-review-agent",
        "issue-workflow-refine-agent",
    ]
    feedback = cfg.agents["handle-feedback-agent"]
    assert feedback.provider == "cursor"
    assert feedback.gate is not None
    assert "list-feedback-issues.sh" in " ".join(feedback.gate.command)
    assert feedback.issues is not None
    assert "list-feedback-issues.sh" in " ".join(feedback.issues.command)
    assert planner.parallel_run == 1
    assert planner.issues is None
    assert "{parallel_id}" in planner.prompt and "{issue}" in planner.prompt
    review = cfg.agents["issue-workflow-review-agent"]
    assert review.parallel_run == 1
    assert review.issues is not None
    assert "status:pending-review" in review.issues.command
    assert "{parallel_id}" in review.prompt and "{issue}" in review.prompt
    assert babysit.issues is None


def _write_agent_config(cfg_dir: Path, body: dict) -> None:
    cfg_dir.mkdir()
    (cfg_dir / "config.yaml").write_text(yaml.dump(body), encoding="utf-8")


def _agent_body(**agent_fields: object) -> dict:
    agent = {
        "skill": "a",
        "provider": "p",
        "enabled": True,
        "prompt": "go",
    }
    agent.update(agent_fields)
    return {
        "providers": {"p": {"command": ["echo"]}},
        "agents": {"a": agent},
    }


def test_omitted_gate_initial_tracks_cooldown(tmp_path: Path) -> None:
    cfg_dir = tmp_path / ".orc"
    body = _agent_body()
    body["orchestrator"] = {"cooldown_seconds": 3}
    _write_agent_config(cfg_dir, body)
    cfg = load_config(cfg_dir)
    assert cfg.orchestrator.cooldown_seconds == 3
    assert cfg.orchestrator.gate_backoff_initial_seconds == 3
    agent = cfg.agents["a"]
    assert resolved_cooldown_seconds(agent, cfg.orchestrator) == 3
    assert resolved_gate_backoff_initial_seconds(agent, cfg.orchestrator) == 3


def test_local_cooldown_override_still_tracks_gate_initial(tmp_path: Path) -> None:
    cfg_dir = tmp_path / ".orc"
    cfg_dir.mkdir()
    (cfg_dir / "config.yaml").write_text(
        yaml.dump(
            {
                "orchestrator": {"cooldown_seconds": 10},
                "providers": {"p": {"command": ["echo"]}},
                "agents": {
                    "a": {
                        "skill": "a",
                        "provider": "p",
                        "enabled": True,
                        "prompt": "go",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (cfg_dir / "config.local.yaml").write_text(
        yaml.dump({"orchestrator": {"cooldown_seconds": 4}}),
        encoding="utf-8",
    )
    cfg = load_config(cfg_dir)
    assert cfg.orchestrator.cooldown_seconds == 4
    assert cfg.orchestrator.gate_backoff_initial_seconds == 4


def test_explicit_gate_initial_stays_when_cooldown_changes(tmp_path: Path) -> None:
    cfg_dir = tmp_path / ".orc"
    cfg_dir.mkdir()
    (cfg_dir / "config.yaml").write_text(
        yaml.dump(
            {
                "orchestrator": {
                    "cooldown_seconds": 10,
                    "gate_backoff_initial_seconds": 10,
                },
                "providers": {"p": {"command": ["echo"]}},
                "agents": {
                    "a": {
                        "skill": "a",
                        "provider": "p",
                        "enabled": True,
                        "prompt": "go",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (cfg_dir / "config.local.yaml").write_text(
        yaml.dump({"orchestrator": {"cooldown_seconds": 3}}),
        encoding="utf-8",
    )
    cfg = load_config(cfg_dir)
    assert cfg.orchestrator.cooldown_seconds == 3
    assert cfg.orchestrator.gate_backoff_initial_seconds == 10


def test_per_agent_timing_falls_back_independently(tmp_path: Path) -> None:
    cfg_dir = tmp_path / ".orc"
    body = _agent_body(cooldown_seconds=30)
    body["orchestrator"] = {
        "cooldown_seconds": 10,
        "gate_backoff_initial_seconds": 15,
        "gate_backoff_max_seconds": 60,
    }
    _write_agent_config(cfg_dir, body)
    cfg = load_config(cfg_dir)
    agent = cfg.agents["a"]
    assert resolved_cooldown_seconds(agent, cfg.orchestrator) == 30
    assert resolved_gate_backoff_initial_seconds(agent, cfg.orchestrator) == 15
    assert resolved_gate_backoff_max_seconds(agent, cfg.orchestrator) == 60


def test_per_agent_timing_override_from_local(tmp_path: Path) -> None:
    cfg_dir = tmp_path / ".orc"
    cfg_dir.mkdir()
    (cfg_dir / "config.yaml").write_text(
        yaml.dump(
            {
                "orchestrator": {"cooldown_seconds": 10, "gate_backoff_max_seconds": 60},
                "providers": {"p": {"command": ["echo"]}},
                "agents": {
                    "a": {
                        "skill": "a",
                        "provider": "p",
                        "enabled": True,
                        "prompt": "go",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (cfg_dir / "config.local.yaml").write_text(
        yaml.dump(
            {
                "agents": {
                    "a": {
                        "cooldown_seconds": 0,
                        "gate_backoff_initial_seconds": 0,
                        "gate_backoff_max_seconds": 120,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    cfg = load_config(cfg_dir)
    agent = cfg.agents["a"]
    assert agent.prompt == "go"
    assert resolved_cooldown_seconds(agent, cfg.orchestrator) == 0
    assert resolved_gate_backoff_initial_seconds(agent, cfg.orchestrator) == 0
    assert resolved_gate_backoff_max_seconds(agent, cfg.orchestrator) == 120


def test_parallel_run_defaults_and_issues_command(tmp_path: Path) -> None:
    cfg_dir = tmp_path / ".orc"
    body = _agent_body(
        parallel_run=3,
        issues={"command": ["gh", "issue", "list", "--json", "number"]},
    )
    _write_agent_config(cfg_dir, body)
    agent = load_config(cfg_dir).agents["a"]
    assert agent.parallel_run == 3
    assert agent.issues is not None
    assert agent.issues.command[0] == "gh"


def test_parallel_run_omitted_is_one(tmp_path: Path) -> None:
    cfg_dir = tmp_path / ".orc"
    _write_agent_config(cfg_dir, _agent_body())
    agent = load_config(cfg_dir).agents["a"]
    assert agent.parallel_run == 1
    assert agent.issues is None


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "2"])
def test_parallel_run_rejected(tmp_path: Path, value: object) -> None:
    cfg_dir = tmp_path / ".orc"
    _write_agent_config(cfg_dir, _agent_body(parallel_run=value))
    with pytest.raises(ConfigError, match="parallel_run"):
        load_config(cfg_dir)


def test_issues_require_command(tmp_path: Path) -> None:
    cfg_dir = tmp_path / ".orc"
    _write_agent_config(cfg_dir, _agent_body(issues={"limit": 10}))
    with pytest.raises(ConfigError, match="issues"):
        load_config(cfg_dir)


def test_negative_timing_rejected(tmp_path: Path) -> None:
    cfg_dir = tmp_path / ".orc"
    body = _agent_body(gate_backoff_initial_seconds=-1)
    _write_agent_config(cfg_dir, body)
    with pytest.raises(ConfigError, match="gate_backoff_initial_seconds"):
        load_config(cfg_dir)


def test_expand_env_in_tree_nested(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORC_MODEL", "opencode-go/custom")
    monkeypatch.delenv("ORC_MISSING", raising=False)
    tree = {
        "providers": {
            "p": {
                "command": [
                    "opencode",
                    "--model",
                    "${ORC_MODEL}",
                    "{prompt}",
                ]
            }
        },
        "agents": {"a": {"prompt": "run ${ORC_MODEL}"}},
        "count": 3,
        "flag": True,
    }
    out = expand_env_in_tree(tree)
    assert out["providers"]["p"]["command"] == [
        "opencode",
        "--model",
        "opencode-go/custom",
        "{prompt}",
    ]
    assert out["agents"]["a"]["prompt"] == "run opencode-go/custom"
    assert out["count"] == 3
    assert out["flag"] is True


def test_expand_env_default_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ORC_MODEL", raising=False)
    assert expand_env_in_tree("${ORC_MODEL:-opencode-go/qwen3.8-max}") == "opencode-go/qwen3.8-max"


def test_expand_env_missing_required_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ORC_REQUIRED", raising=False)
    with pytest.raises(ConfigError, match="Unset environment variable: ORC_REQUIRED"):
        expand_env_in_tree("${ORC_REQUIRED}")


def test_load_config_expands_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORC_TEST_MODEL", "opencode-go/from-env")
    monkeypatch.setenv("ORC_TEST_LOGS", "/tmp/orc-logs")
    cfg_dir = tmp_path / ".orc"
    cfg_dir.mkdir()
    (cfg_dir / "config.yaml").write_text(
        yaml.dump(
            {
                "orchestrator": {"logs_dir": "${ORC_TEST_LOGS}"},
                "providers": {
                    "p": {
                        "command": [
                            "opencode",
                            "run",
                            "--model",
                            "${ORC_TEST_MODEL}",
                            "{prompt}",
                        ]
                    }
                },
                "agents": {
                    "a": {
                        "skill": "a",
                        "provider": "p",
                        "enabled": True,
                        "prompt": "use ${ORC_TEST_MODEL}",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    cfg = load_config(cfg_dir)
    assert cfg.orchestrator.logs_dir == "/tmp/orc-logs"
    assert cfg.providers["p"] == [
        "opencode",
        "run",
        "--model",
        "opencode-go/from-env",
        "{prompt}",
    ]
    assert cfg.agents["a"].prompt == "use opencode-go/from-env"


def test_load_config_literal_only_unchanged(tmp_path: Path) -> None:
    cfg_dir = tmp_path / ".orc"
    body = _agent_body()
    body["providers"]["p"]["command"] = ["opencode", "run", "--model", "literal", "{prompt}"]
    _write_agent_config(cfg_dir, body)
    cfg = load_config(cfg_dir)
    assert cfg.providers["p"] == ["opencode", "run", "--model", "literal", "{prompt}"]
    assert cfg.agents["a"].prompt == "go"


def _chain_config(
    *,
    leaf_enabled: bool = True,
    chain: list | None = None,
    composite_extra: dict | None = None,
) -> dict:
    body: dict = {
        "providers": {"p": {"command": ["echo"]}, "q": {"command": ["echo"]}},
        "agents": {
            "leaf-a": {
                "skill": "leaf-a",
                "provider": "p",
                "enabled": leaf_enabled,
                "prompt": "run a",
                "cooldown_seconds": 7,
                "gate": {"command": ["true"]},
            },
            "leaf-b": {
                "skill": "leaf-b",
                "provider": "q",
                "enabled": True,
                "prompt": "run b",
            },
            "chain-ab": {
                "enabled": True,
                "cooldown_seconds": 30,
                "chain": chain
                if chain is not None
                else [
                    "leaf-a",
                    {
                        "skill": "inline-c",
                        "provider": "p",
                        "prompt": "run inline",
                        "cooldown_seconds": 2,
                    },
                ],
            },
        },
    }
    if composite_extra:
        body["agents"]["chain-ab"].update(composite_extra)
    return body


def test_parse_composite_refs_and_inline(tmp_path: Path) -> None:
    cfg_dir = tmp_path / ".orc"
    _write_agent_config(cfg_dir, _chain_config())
    cfg = load_config(cfg_dir)
    composite = cfg.agents["chain-ab"]
    assert is_composite(composite)
    assert not is_composite(cfg.agents["leaf-a"])
    assert composite.chain is not None
    assert len(composite.chain) == 2
    assert composite.cooldown_seconds == 30
    step0 = composite.chain[0]
    assert step0.name == "chain-ab:leaf-a"
    assert step0.skill == "leaf-a"
    assert step0.provider == "p"
    assert step0.prompt == "run a"
    assert step0.cooldown_seconds == 7
    assert step0.gate is not None
    step1 = composite.chain[1]
    assert step1.name == "chain-ab:step-2"
    assert step1.skill == "inline-c"
    assert step1.cooldown_seconds == 2


def test_composite_ref_allows_disabled_leaf(tmp_path: Path) -> None:
    cfg_dir = tmp_path / ".orc"
    _write_agent_config(cfg_dir, _chain_config(leaf_enabled=False, chain=["leaf-a"]))
    cfg = load_config(cfg_dir)
    assert cfg.agents["leaf-a"].enabled is False
    assert cfg.agents["chain-ab"].chain is not None
    assert cfg.agents["chain-ab"].chain[0].skill == "leaf-a"
    assert [a.name for a in enabled_agents(cfg)] == ["leaf-b", "chain-ab"]


def test_composite_rejects_empty_chain(tmp_path: Path) -> None:
    cfg_dir = tmp_path / ".orc"
    _write_agent_config(cfg_dir, _chain_config(chain=[]))
    with pytest.raises(ConfigError, match="non-empty"):
        load_config(cfg_dir)


def test_composite_rejects_unknown_ref(tmp_path: Path) -> None:
    cfg_dir = tmp_path / ".orc"
    _write_agent_config(cfg_dir, _chain_config(chain=["missing"]))
    with pytest.raises(ConfigError, match="unknown or not a leaf"):
        load_config(cfg_dir)


def test_composite_rejects_nested_chain_ref(tmp_path: Path) -> None:
    cfg_dir = tmp_path / ".orc"
    body = _chain_config(chain=["leaf-a"])
    body["agents"]["outer"] = {"enabled": True, "chain": ["chain-ab"]}
    _write_agent_config(cfg_dir, body)
    with pytest.raises(ConfigError, match="unknown or not a leaf"):
        load_config(cfg_dir)


def test_composite_rejects_leaf_fields(tmp_path: Path) -> None:
    cfg_dir = tmp_path / ".orc"
    _write_agent_config(cfg_dir, _chain_config(composite_extra={"skill": "nope"}))
    with pytest.raises(ConfigError, match="must not set skill"):
        load_config(cfg_dir)


def test_composite_rejects_issues(tmp_path: Path) -> None:
    cfg_dir = tmp_path / ".orc"
    _write_agent_config(
        cfg_dir,
        _chain_config(composite_extra={"issues": {"command": ["echo", "[]"]}}),
    )
    with pytest.raises(ConfigError, match="must not set issues"):
        load_config(cfg_dir)


def test_leaf_rejects_chain_mix_via_inline(tmp_path: Path) -> None:
    cfg_dir = tmp_path / ".orc"
    _write_agent_config(
        cfg_dir,
        _chain_config(
            chain=[
                {
                    "skill": "x",
                    "provider": "p",
                    "prompt": "x",
                    "chain": ["leaf-a"],
                }
            ]
        ),
    )
    with pytest.raises(ConfigError, match="must not set chain"):
        load_config(cfg_dir)


def test_schedules_parse_and_allow_agent_in_multiple(tmp_path: Path) -> None:
    cfg_dir = tmp_path / ".orc"
    body = _agent_body()
    body["orchestrator"] = {"schedule_poll_seconds": 2}
    body["schedules"] = {
        "morning": {"cron": "0 8 * * *", "agents": ["a"]},
        "evening": {"cron": "0 18 * * *", "agents": ["a"]},
    }
    _write_agent_config(cfg_dir, body)
    cfg = load_config(cfg_dir)
    assert cfg.orchestrator.schedule_poll_seconds == 2
    assert set(cfg.schedules) == {"morning", "evening"}
    assert cfg.schedules["morning"].agents == ["a"]
    assert cfg.schedules["evening"].cron == "0 18 * * *"


def test_schedule_unknown_agent(tmp_path: Path) -> None:
    cfg_dir = tmp_path / ".orc"
    body = _agent_body()
    body["schedules"] = {"bad": {"cron": "* * * * *", "agents": ["missing"]}}
    _write_agent_config(cfg_dir, body)
    with pytest.raises(ConfigError, match="unknown agent"):
        load_config(cfg_dir)


def test_schedule_invalid_cron(tmp_path: Path) -> None:
    cfg_dir = tmp_path / ".orc"
    body = _agent_body()
    body["schedules"] = {"bad": {"cron": "not-a-cron", "agents": ["a"]}}
    _write_agent_config(cfg_dir, body)
    with pytest.raises(ConfigError, match="not a valid cron"):
        load_config(cfg_dir)


def test_schedule_requires_agents(tmp_path: Path) -> None:
    cfg_dir = tmp_path / ".orc"
    body = _agent_body()
    body["schedules"] = {"bad": {"cron": "* * * * *", "agents": []}}
    _write_agent_config(cfg_dir, body)
    with pytest.raises(ConfigError, match="non-empty list"):
        load_config(cfg_dir)
