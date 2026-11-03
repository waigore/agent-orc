"""Thin gh CLI wrapper (e2e and helpers)."""

from __future__ import annotations

import json
import subprocess
from typing import Any


class GhError(Exception):
    """gh command failed."""


def run_gh(args: list[str], *, cwd: str | None = None) -> str:
    completed = subprocess.run(
        ["gh", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise GhError(completed.stderr.strip() or completed.stdout.strip())
    return completed.stdout.strip()


def create_issue(
    title: str,
    body: str,
    labels: list[str],
    *,
    cwd: str | None = None,
) -> int:
    args = ["issue", "create", "--title", title, "--body", body]
    for label in labels:
        args.extend(["--label", label])
    url = run_gh(args, cwd=cwd)
    # URL ends with /issues/N
    number = int(url.rstrip("/").split("/")[-1])
    return number


def issue_labels(number: int, *, cwd: str | None = None) -> list[str]:
    raw = run_gh(
        ["issue", "view", str(number), "--json", "labels"],
        cwd=cwd,
    )
    data: dict[str, Any] = json.loads(raw)
    return [item["name"] for item in data.get("labels", [])]


def issue_status_label(number: int, *, cwd: str | None = None) -> str | None:
    labels = issue_labels(number, cwd=cwd)
    for name in labels:
        if name.startswith("status:"):
            return name
    return None


def close_issue(number: int, *, cwd: str | None = None) -> None:
    run_gh(["issue", "close", str(number)], cwd=cwd)


def gh_available() -> bool:
    try:
        run_gh(["auth", "status"])
        return True
    except (GhError, FileNotFoundError):
        return False
