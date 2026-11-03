from __future__ import annotations

from pathlib import Path

import pytest

from agent_orc.config import load_config
from agent_orc.crew.factory import build_crew, run_skill_once
from agent_orc.crew.tools import run_provider_command
from helpers import write_test_config


def test_run_provider_command_writes_log(
    temp_git_repo: Path, fake_cli: Path, tmp_path: Path
) -> None:
    log_path = tmp_path / "run.log"
    code = run_provider_command(
        ["python3", str(fake_cli), "skill"],
        workdir=temp_git_repo,
        log_path=log_path,
    )
    assert code == 0
    assert "fake-agent ok" in log_path.read_text(encoding="utf-8")


def test_run_provider_nonzero(
    temp_git_repo: Path, fake_cli: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ORC_FAKE_EXIT", "7")
    log_path = tmp_path / "run.log"
    code = run_provider_command(
        ["python3", str(fake_cli)],
        workdir=temp_git_repo,
        log_path=log_path,
    )
    assert code == 7


def test_build_crew_and_run_skill_once(temp_git_repo: Path, fake_cli: Path, tmp_path: Path) -> None:
    cfg_dir = tmp_path / ".orc"
    write_test_config(cfg_dir, fake_cli=fake_cli, agents=["project-planner-agent"])
    config = load_config(cfg_dir)
    agent = config.agents["project-planner-agent"]
    logs = tmp_path / "logs"
    crew, tool, session_id = build_crew(
        agent, config, workdir=temp_git_repo, log_path=logs / "x.log"
    )
    assert crew is not None
    assert tool.command[0] == "python3"
    assert session_id is None
    code = run_skill_once(agent, config, workdir=temp_git_repo, logs_dir=logs)
    assert code == 0
    runs = list((logs / "project-planner-agent").glob("run-*.log"))
    assert len(runs) == 1
