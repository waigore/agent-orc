from __future__ import annotations

from pathlib import Path

import pytest

from agent_orc.providers.opencode import (
    bind_session,
    command_session_id,
    delete_session,
    ensure_session_flag,
    is_opencode_command,
)
from agent_orc.shutdown import OpenCodeSessionRef, ShutdownController


def test_is_opencode_command() -> None:
    assert is_opencode_command(["opencode", "run", "--auto", "hi"])
    assert is_opencode_command(["/usr/local/bin/opencode", "run", "hi"])
    assert not is_opencode_command(["cursor-agent", "-p", "hi"])
    assert not is_opencode_command([])


def test_ensure_session_flag_inserts_after_run() -> None:
    out = ensure_session_flag(["opencode", "run", "--auto", "hello"], "ses_orc_abc")
    assert out == [
        "opencode",
        "run",
        "--session",
        "ses_orc_abc",
        "--auto",
        "hello",
    ]


def test_ensure_session_flag_keeps_existing() -> None:
    cmd = ["opencode", "run", "--session", "ses_existing", "--auto", "hi"]
    assert ensure_session_flag(cmd, "ses_other") == cmd
    assert command_session_id(cmd) == "ses_existing"


def test_bind_session_for_opencode() -> None:
    cmd, sid = bind_session(["opencode", "run", "--auto", "hi"])
    assert sid is not None
    assert sid.startswith("ses_orc_")
    assert command_session_id(cmd) == sid


def test_bind_session_ignores_other_providers() -> None:
    cmd, sid = bind_session(["grok", "-p", "hi"])
    assert sid is None
    assert cmd == ["grok", "-p", "hi"]


def test_delete_session_invokes_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    class Result:
        returncode = 0
        stdout = "Session ses_x deleted"
        stderr = ""

    def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(list(cmd))
        assert kwargs.get("cwd") == str(tmp_path)
        return Result()

    monkeypatch.setattr("agent_orc.providers.opencode.subprocess.run", fake_run)
    delete_session("ses_x", cwd=tmp_path, binary="opencode")
    assert calls == [["opencode", "session", "delete", "ses_x"]]


def test_force_shutdown_deletes_opencode_sessions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    deleted: list[str] = []

    def fake_delete(session_id: str, *, cwd=None, binary="opencode") -> None:  # type: ignore[no-untyped-def]
        deleted.append(session_id)

    monkeypatch.setattr("agent_orc.shutdown.delete_opencode_session", fake_delete)
    # Avoid real killpg on fake pids
    monkeypatch.setattr("agent_orc.shutdown.os.killpg", lambda *_a, **_k: None)
    monkeypatch.setattr("agent_orc.shutdown.os.kill", lambda *_a, **_k: None)
    monkeypatch.setattr("agent_orc.shutdown.delete_worktree", lambda *_a, **_k: None)

    ctl = ShutdownController()
    ctl.active_pids.add(12345)
    ctl.register_opencode_session(OpenCodeSessionRef(session_id="ses_orc_one", cwd=tmp_path))
    ctl.register_opencode_session(OpenCodeSessionRef(session_id="ses_orc_two", cwd=tmp_path))
    ctl.force_shutdown()
    assert deleted == ["ses_orc_one", "ses_orc_two"]
    assert ctl.active_opencode_sessions == []
    assert ctl.shutting_down is True
