"""In-memory issue ownership for parallel slots of one daemon process."""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger("agent_orc.assignment")

UNASSIGNED_ISSUE = "none"


class IssueListError(Exception):
    """issues.command failed or printed something other than issue numbers."""


class IssueOwnership:
    """Daemon-wide map from issue number to the slot that currently owns it."""

    def __init__(self) -> None:
        self._owners: dict[int, str] = {}
        self._lock = asyncio.Lock()

    async def claim(self, owner: str, candidates: list[int]) -> int | None:
        """Assign the first free candidate in list order. None if all are taken.

        Callers pass candidates already ordered (e.g. priority then number).
        Duplicates in the list are skipped after the first occurrence.
        """
        async with self._lock:
            seen: set[int] = set()
            for number in candidates:
                if number in seen:
                    continue
                seen.add(number)
                if number not in self._owners:
                    self._owners[number] = owner
                    logger.info("claimed issue %s for %s", number, owner)
                    return number
            return None

    async def release(self, owner: str) -> None:
        """Drop every issue owned by this slot. Safe when the slot owns nothing."""
        async with self._lock:
            released = [n for n, who in self._owners.items() if who == owner]
            for number in released:
                del self._owners[number]
                logger.info("released issue %s from %s", number, owner)


def render_agent_prompt(prompt: str, *, parallel_id: int, issue: str) -> str:
    """Fill {parallel_id} and {issue}. Unassigned work uses issue 'none'."""
    return prompt.replace("{parallel_id}", str(parallel_id)).replace("{issue}", issue)


def parse_issue_numbers(stdout: str) -> list[int]:
    """Parse `gh issue list --json number` output: a JSON array of {number}."""
    text = stdout.strip()
    if not text:
        raise IssueListError("issues command printed no JSON")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise IssueListError("issues command did not print JSON") from exc
    if not isinstance(data, list):
        raise IssueListError("issues command must print a JSON array")
    numbers: list[int] = []
    for item in data:
        if not isinstance(item, dict) or "number" not in item:
            raise IssueListError("each issue must be an object with number")
        number = item["number"]
        if isinstance(number, bool) or not isinstance(number, int) or number < 1:
            raise IssueListError(f"invalid issue number: {number!r}")
        numbers.append(number)
    return numbers


def list_issue_numbers(command: list[str], *, cwd: Path) -> list[int]:
    """Run issues.command and return the issue numbers it printed."""
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise IssueListError(f"issues command not found: {command[0]}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise IssueListError(detail or f"issues command exited {completed.returncode}")
    return parse_issue_numbers(completed.stdout)
