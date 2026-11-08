"""Hermes Agent CLI provider: project-skills trust before runs."""

from __future__ import annotations

import logging
import subprocess
from collections.abc import Sequence
from pathlib import Path

PROVIDER_NAME = "hermes"

logger = logging.getLogger("agent_orc.providers.hermes")


def is_hermes_command(command: Sequence[str]) -> bool:
    if not command:
        return False
    binary = Path(command[0]).name
    return binary == "hermes" or binary.startswith("hermes.")


def trust_project_skills(
    *paths: Path | str | None,
    binary: str = "hermes",
) -> None:
    """
    Best-effort `hermes skills trust <path>` for each unique path.

    Hermes will not load project skills under `.hermes/skills/` /
    `.agents/skills/` until the checkout is trusted. Failures are logged and
    never raised so the agent run can still proceed.
    """
    seen: set[Path] = set()
    for raw in paths:
        if raw is None:
            continue
        path = Path(raw).resolve()
        if path in seen:
            continue
        seen.add(path)
        _trust_one(path, binary=binary)


def _trust_one(path: Path, *, binary: str) -> None:
    cmd = [binary, "skills", "trust", str(path)]
    try:
        completed = subprocess.run(
            cmd,
            cwd=str(path) if path.is_dir() else None,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        logger.warning("hermes binary not found; cannot trust project skills at %s", path)
        return
    except OSError as exc:
        logger.warning("failed to trust hermes project skills at %s: %s", path, exc)
        return
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        logger.warning(
            "hermes skills trust %s exited %s: %s",
            path,
            completed.returncode,
            detail or "(no output)",
        )
        return
    logger.info("trusted hermes project skills at %s", path)
