"""Git worktree create/delete and pull on the orchestrator checkout."""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger("agent_orc.worktree")


class WorktreeError(Exception):
    """Git worktree operation failed."""


@dataclass
class WorktreeSession:
    path: Path
    branch: str
    repo_root: Path


def _run_git(
    args: list[str],
    *,
    cwd: Path,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    if check and completed.returncode != 0:
        raise WorktreeError(
            f"git {' '.join(args)} failed: {completed.stderr.strip() or completed.stdout}"
        )
    return completed


def pull_repo(repo_root: Path, branch: str) -> None:
    logger.info("pulling %s on %s", branch, repo_root)
    _run_git(["fetch", "origin", branch], cwd=repo_root, check=False)
    _run_git(["pull", "--ff-only", "origin", branch], cwd=repo_root, check=False)


def create_worktree(
    repo_root: Path,
    worktrees_dir: Path,
    agent_name: str,
    *,
    base_branch: str = "main",
) -> WorktreeSession:
    worktrees_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    safe = agent_name.replace("/", "-")
    branch = f"orc/{safe}/{stamp}"
    path = worktrees_dir / f"{safe}-{stamp}"
    if path.exists():
        raise WorktreeError(f"worktree path already exists: {path}")
    _run_git(
        ["worktree", "add", "-b", branch, str(path), base_branch],
        cwd=repo_root,
    )
    logger.info("created worktree %s (branch %s)", path, branch)
    return WorktreeSession(path=path, branch=branch, repo_root=repo_root)


def delete_worktree(session: WorktreeSession | None) -> None:
    if session is None:
        return
    path = session.path
    repo_root = session.repo_root
    branch = session.branch
    if path.exists():
        completed = _run_git(
            ["worktree", "remove", "--force", str(path)],
            cwd=repo_root,
            check=False,
        )
        if completed.returncode != 0 and path.exists():
            shutil.rmtree(path, ignore_errors=True)
            _run_git(["worktree", "prune"], cwd=repo_root, check=False)
    if branch:
        _run_git(["branch", "-D", branch], cwd=repo_root, check=False)
    logger.info("deleted worktree %s (branch %s)", path, branch)
