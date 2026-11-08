from __future__ import annotations

from pathlib import Path

import pytest

from agent_orc.config import load_config
from agent_orc.crew.factory import run_skill_once
from agent_orc.providers.hermes import is_hermes_command, trust_project_skills
from helpers import write_test_config


def test_is_hermes_command() -> None:
    assert is_hermes_command(["hermes", "-z", "hi"])
    assert is_hermes_command(["/usr/local/bin/hermes", "-z", "hi"])
    assert is_hermes_command(["hermes.local", "-z", "hi"])
    assert not is_hermes_command(["cursor-agent", "-p", "hi"])
    assert not is_hermes_command([])


def test_trust_project_skills_invokes_cli_for_unique_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    worktree = tmp_path / "wt"
    repo = tmp_path / "repo"
    worktree.mkdir()
    repo.mkdir()
    calls: list[list[str]] = []

    class Result:
        returncode = 0
        stdout = "trusted"
        stderr = ""

    def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(list(cmd))
        return Result()

    monkeypatch.setattr("agent_orc.providers.hermes.subprocess.run", fake_run)
    trust_project_skills(worktree, repo, worktree, binary="hermes")
    assert calls == [
        ["hermes", "skills", "trust", str(worktree.resolve())],
        ["hermes", "skills", "trust", str(repo.resolve())],
    ]


def test_trust_project_skills_logs_and_continues_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "proj"
    path.mkdir()

    class Result:
        returncode = 2
        stdout = ""
        stderr = "denied"

    monkeypatch.setattr(
        "agent_orc.providers.hermes.subprocess.run",
        lambda *a, **k: Result(),  # type: ignore[no-untyped-def]
    )
    with caplog.at_level("WARNING", logger="agent_orc.providers.hermes"):
        trust_project_skills(path)
    assert any("exited 2" in r.message for r in caplog.records)


def test_trust_project_skills_missing_binary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "proj"
    path.mkdir()

    def boom(*a, **k):  # type: ignore[no-untyped-def]
        raise FileNotFoundError("hermes")

    monkeypatch.setattr("agent_orc.providers.hermes.subprocess.run", boom)
    with caplog.at_level("WARNING", logger="agent_orc.providers.hermes"):
        trust_project_skills(path)
    assert any("hermes binary not found" in r.message for r in caplog.records)


def test_run_skill_once_trusts_before_hermes(
    temp_git_repo: Path, fake_cli: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg_dir = tmp_path / ".orc"
    write_test_config(cfg_dir, fake_cli=fake_cli, agents=["project-planner-agent"])
    config = load_config(cfg_dir)
    agent = config.agents["project-planner-agent"]
    config.providers[agent.provider] = ["hermes", "-z", "{prompt}", "-s", "{skill}"]

    trusted: list[tuple] = []
    order: list[str] = []

    def fake_trust(*paths, binary="hermes"):  # type: ignore[no-untyped-def]
        order.append("trust")
        trusted.append((tuple(str(Path(p).resolve()) for p in paths if p is not None), binary))

    def fake_run(command, *, workdir, log_path, on_pid=None, on_pid_done=None):  # type: ignore[no-untyped-def]
        order.append("run")
        assert command[0] == "hermes"
        return 0

    monkeypatch.setattr("agent_orc.crew.factory.trust_project_skills", fake_trust)
    monkeypatch.setattr("agent_orc.crew.factory.run_provider_command", fake_run)

    repo_root = tmp_path / "repo-root"
    repo_root.mkdir()
    code = run_skill_once(
        agent,
        config,
        workdir=temp_git_repo,
        logs_dir=tmp_path / "logs",
        repo_root=repo_root,
    )
    assert code == 0
    assert order == ["trust", "run"]
    assert trusted == [
        (
            (str(temp_git_repo.resolve()), str(repo_root.resolve())),
            "hermes",
        )
    ]


def test_run_skill_once_skips_trust_for_non_hermes(
    temp_git_repo: Path, fake_cli: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg_dir = tmp_path / ".orc"
    write_test_config(cfg_dir, fake_cli=fake_cli, agents=["project-planner-agent"])
    config = load_config(cfg_dir)
    agent = config.agents["project-planner-agent"]
    called = False

    def fake_trust(*a, **k):  # type: ignore[no-untyped-def]
        nonlocal called
        called = True

    monkeypatch.setattr("agent_orc.crew.factory.trust_project_skills", fake_trust)
    code = run_skill_once(agent, config, workdir=temp_git_repo, logs_dir=tmp_path / "logs")
    assert code == 0
    assert called is False
