from __future__ import annotations

from pathlib import Path

import pytest

from agent_orc.cli import build_parser, run
from helpers import write_test_config


def test_cli_smoke_all_eight(
    temp_git_repo: Path, fake_cli: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ORC_FAKE_RECORD", str(tmp_path / "r.jsonl"))
    monkeypatch.chdir(temp_git_repo)
    names = [
        "project-planner-agent",
        "issue-workflow-review-agent",
        "issue-workflow-refine-agent",
        "issue-workflow-clarify-agent",
        "issue-workflow-implement-agent",
        "issue-workflow-verify-agent",
        "issue-workflow-accept-agent",
        "babysit-pr-agent",
    ]
    cfg_dir = temp_git_repo / ".orc"
    write_test_config(
        cfg_dir,
        fake_cli=fake_cli,
        agents=names,
        cooldown=0,
        stagger=0,
    )
    args = build_parser().parse_args(
        ["-n", "1", "--yes", "--config-dir", str(cfg_dir), "--repo-root", str(temp_git_repo)]
    )
    code = run(args)
    assert code == 0
    for name in names:
        logs = list((temp_git_repo / ".orc" / "logs" / name).glob("run-*.log"))
        assert len(logs) == 1, name
    wt = temp_git_repo / ".orc" / "worktrees"
    assert not wt.exists() or not any(wt.iterdir())
