from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from agent_orc.config import load_config
from agent_orc.shutdown import ShutdownController
from agent_orc.supervisor import run_supervisor
from helpers import write_test_config


@pytest.mark.asyncio
async def test_force_shutdown_kills_and_purges(
    temp_git_repo: Path, fake_cli: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ORC_FAKE_DELAY", "5")
    monkeypatch.setenv("ORC_FAKE_RECORD", str(tmp_path / "r.jsonl"))
    cfg_dir = temp_git_repo / ".orc"
    write_test_config(
        cfg_dir,
        fake_cli=fake_cli,
        agents=["project-planner-agent"],
        cooldown=0,
        stagger=0,
    )
    config = load_config(cfg_dir)
    shutdown = ShutdownController()

    async def force() -> None:
        await asyncio.sleep(0.3)
        shutdown.force_shutdown()

    task = asyncio.create_task(
        run_supervisor(
            config,
            [config.agents["project-planner-agent"]],
            count=1,
            shutdown=shutdown,
            repo_root=temp_git_repo,
        )
    )
    await force()
    # skill loop should exit soon after shutting_down
    try:
        await asyncio.wait_for(task, timeout=3)
    except TimeoutError:
        task.cancel()
        pytest.fail("supervisor did not stop after force_shutdown")
    wt = temp_git_repo / ".orc" / "worktrees"
    assert not wt.exists() or not any(wt.iterdir())


def test_confirm_false_resets(monkeypatch: pytest.MonkeyPatch) -> None:
    ctl = ShutdownController(confirm_fn=lambda _m: False)
    ctl.active_pids.add(os_get_fake_pid())
    # simulate first SIGINT with confirm false — should not set shutting_down
    import sys

    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    try:
        ctl._handle_sigint(2, None)
    except SystemExit:
        pytest.fail("should not exit when confirm is False")
    assert ctl.shutting_down is False
    assert ctl._force_count == 0


def os_get_fake_pid() -> int:
    return 1
