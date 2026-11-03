from __future__ import annotations

from agent_orc.config import AgentConfig, GateConfig
from agent_orc.gate import gate_passes, next_gate_backoff


def test_no_gate_passes() -> None:
    agent = AgentConfig(name="a", skill="a", provider="p", enabled=True, prompt="x", gate=None)
    assert gate_passes(agent) is True


def test_gate_exit_zero() -> None:
    agent = AgentConfig(
        name="a",
        skill="a",
        provider="p",
        enabled=True,
        prompt="x",
        gate=GateConfig(command=["true"]),
    )
    assert gate_passes(agent) is True


def test_gate_exit_nonzero() -> None:
    agent = AgentConfig(
        name="a",
        skill="a",
        provider="p",
        enabled=True,
        prompt="x",
        gate=GateConfig(command=["false"]),
    )
    assert gate_passes(agent) is False


def test_gate_command_not_found() -> None:
    agent = AgentConfig(
        name="a",
        skill="a",
        provider="p",
        enabled=True,
        prompt="x",
        gate=GateConfig(command=["orc-nonexistent-binary-xyz"]),
    )
    assert gate_passes(agent) is False


def test_backoff_doubles_and_caps() -> None:
    assert next_gate_backoff(0, initial=10, maximum=60, consecutive_misses=1) == 10
    assert next_gate_backoff(0, initial=10, maximum=60, consecutive_misses=2) == 20
    assert next_gate_backoff(0, initial=10, maximum=60, consecutive_misses=3) == 40
    assert next_gate_backoff(0, initial=10, maximum=60, consecutive_misses=4) == 60
    assert next_gate_backoff(0, initial=10, maximum=60, consecutive_misses=5) == 60


def test_backoff_zero_initial_stays_zero() -> None:
    assert next_gate_backoff(0, initial=0, maximum=60, consecutive_misses=1) == 0
    assert next_gate_backoff(0, initial=0, maximum=60, consecutive_misses=5) == 0
