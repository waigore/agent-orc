from __future__ import annotations

import sys
from pathlib import Path

import pytest

from agent_orc.config import load_config
from agent_orc.crew.factory import build_crew, run_skill_once
from agent_orc.crew.tools import provider_cli_env, run_provider_command
from helpers import write_test_config


def test_provider_cli_env_sets_pwd_to_workdir(tmp_path: Path) -> None:
    workdir = tmp_path / "wt"
    workdir.mkdir()
    env = provider_cli_env(workdir, base={"PATH": "/bin", "PWD": "/somewhere/else"})
    assert env["PWD"] == str(workdir.resolve())
    assert env["PATH"] == "/bin"


def test_run_provider_command_syncs_pwd(
    temp_git_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """OpenCode uses $PWD; Popen(cwd=) alone must not leave a stale value."""
    monkeypatch.setenv("PWD", "/stale/orchestrator/cwd")
    log_path = tmp_path / "pwd.log"
    script = (
        "import os, sys\n"
        "sys.stdout.write(os.environ.get('PWD', '') + '\\n')\n"
        "sys.stdout.write(os.getcwd() + '\\n')\n"
    )
    code = run_provider_command(
        [sys.executable, "-c", script],
        workdir=temp_git_repo,
        log_path=log_path,
    )
    assert code == 0
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert lines[0] == str(temp_git_repo.resolve())
    assert lines[1] == str(temp_git_repo.resolve())


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
