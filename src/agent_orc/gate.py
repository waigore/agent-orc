"""Run per-agent gate commands (exit 0 = pass)."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from agent_orc.config import AgentConfig, GateConfig

logger = logging.getLogger("agent_orc.gate")


def gate_passes(
    agent: AgentConfig,
    *,
    cwd: Path | None = None,
) -> bool:
    """Return True if agent has no gate or gate.command exits 0."""
    gate: GateConfig | None = agent.gate
    if gate is None:
        return True
    try:
        completed = subprocess.run(
            gate.command,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        logger.warning("gate command not found for %s: %s", agent.name, gate.command)
        return False
    if completed.stdout:
        logger.debug("gate %s stdout: %s", agent.name, completed.stdout.strip())
    if completed.stderr:
        logger.debug("gate %s stderr: %s", agent.name, completed.stderr.strip())
    passed = completed.returncode == 0
    if not passed:
        logger.info("gate miss for %s (exit %s)", agent.name, completed.returncode)
    return passed


def next_gate_backoff(
    current: float,
    *,
    initial: float,
    maximum: float,
    consecutive_misses: int,
) -> float:
    """Backoff: initial * 2^(misses-1), capped at maximum. misses starts at 1."""
    if consecutive_misses <= 0:
        return min(initial, maximum)
    delay = initial * (2 ** (consecutive_misses - 1))
    return min(delay, maximum)
