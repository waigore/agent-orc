from __future__ import annotations

from pathlib import Path

from agent_orc.worktree import create_worktree, delete_worktree


def test_create_and_delete(temp_git_repo: Path) -> None:
    wt_dir = temp_git_repo / ".orc" / "worktrees"
    session = create_worktree(temp_git_repo, wt_dir, "issue-workflow-review-agent")
    assert session.path.is_dir()
    assert (session.path / "README.md").is_file()
    assert session.branch.startswith("orc/")
    delete_worktree(session)
    assert not session.path.exists()
    # idempotent
    delete_worktree(session)
