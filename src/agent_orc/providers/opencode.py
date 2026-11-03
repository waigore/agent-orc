"""OpenCode CLI provider: command detection, session bind, session delete."""

from __future__ import annotations

import logging
import subprocess
import uuid
from collections.abc import Sequence
from pathlib import Path

PROVIDER_NAME = "opencode"

logger = logging.getLogger("agent_orc.providers.opencode")


def is_opencode_command(command: Sequence[str]) -> bool:
    if not command:
        return False
    binary = Path(command[0]).name
    return binary == "opencode" or binary.startswith("opencode.")


def new_session_id() -> str:
    return f"ses_orc_{uuid.uuid4().hex[:20]}"


def command_session_id(command: Sequence[str]) -> str | None:
    """Return existing --session / -s value if present."""
    i = 0
    while i < len(command):
        part = command[i]
        if part in {"--session", "-s"} and i + 1 < len(command):
            return command[i + 1]
        if part.startswith("--session="):
            return part.split("=", 1)[1]
        i += 1
    return None


def ensure_session_flag(command: Sequence[str], session_id: str) -> list[str]:
    """
    Ensure `opencode run … --session <id> …`.

    If --session/-s is already set, leave the argv unchanged.
    """
    cmd = list(command)
    if command_session_id(cmd) is not None:
        return cmd
    try:
        run_at = cmd.index("run")
    except ValueError:
        # No `run` subcommand — append flags before any trailing prompt-like args.
        return cmd + ["--session", session_id]
    return cmd[: run_at + 1] + ["--session", session_id] + cmd[run_at + 1 :]


def bind_session(command: Sequence[str]) -> tuple[list[str], str | None]:
    """
    For an OpenCode CLI argv, ensure a session id and return (argv, session_id).

    Non-OpenCode commands are returned unchanged with session_id None.
    """
    cmd = list(command)
    if not is_opencode_command(cmd):
        return cmd, None
    existing = command_session_id(cmd)
    if existing is not None:
        return cmd, existing
    session_id = new_session_id()
    return ensure_session_flag(cmd, session_id), session_id


def delete_session(
    session_id: str,
    *,
    cwd: Path | str | None = None,
    binary: str = "opencode",
) -> None:
    """Best-effort `opencode session delete <id>` so the server will not respawn it."""
    cmd = [binary, "session", "delete", session_id]
    try:
        completed = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd is not None else None,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        logger.warning("opencode binary not found; cannot delete session %s", session_id)
        return
    except OSError as exc:
        logger.warning("failed to delete opencode session %s: %s", session_id, exc)
        return
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        # Interrupt path may delete before the run's finally; treat missing as done.
        if "not found" in detail.lower():
            logger.info("opencode session %s already gone", session_id)
            return
        logger.warning(
            "opencode session delete %s exited %s: %s",
            session_id,
            completed.returncode,
            detail or "(no output)",
        )
        return
    logger.info("deleted opencode session %s", session_id)
