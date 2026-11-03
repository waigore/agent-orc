"""Orchestrator and per-agent run logging."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path


def setup_orchestrator_logging(logs_dir: Path) -> Path:
    logs_dir.mkdir(parents=True, exist_ok=True)
    path = logs_dir / "orchestrator.log"
    root = logging.getLogger("agent_orc")
    root.setLevel(logging.DEBUG)
    root.handlers.clear()

    fmt = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    fh = logging.FileHandler(path, encoding="utf-8")
    fh.setFormatter(fmt)
    fh.setLevel(logging.DEBUG)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    sh.setLevel(logging.INFO)
    root.addHandler(fh)
    root.addHandler(sh)
    return path


def agent_run_log_path(logs_dir: Path, agent_name: str, parallel_id: int = 1) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    directory = logs_dir / agent_name
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"run-{parallel_id}-{stamp}.log"


def agent_logger(agent_name: str) -> logging.Logger:
    return logging.getLogger(f"agent_orc.agent.{agent_name}")
