"""CrewAI tool that runs a configured provider CLI in a worktree."""

from __future__ import annotations

import logging
import os
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path

from crewai.tools import BaseTool
from pydantic import Field, PrivateAttr

logger = logging.getLogger("agent_orc.crew.tools")


def provider_cli_env(workdir: Path, *, base: Mapping[str, str] | None = None) -> dict[str, str]:
    """
    Env for a provider CLI launched in ``workdir``.

    OpenCode (v2.x) resolves the project from ``$PWD``, not ``getcwd()``.
    ``Popen(cwd=...)`` alone leaves a stale ``PWD`` from the orchestrator
    process, so agents run against the wrong tree.
    """
    env = dict(base if base is not None else os.environ)
    resolved = str(workdir.resolve())
    env["PWD"] = resolved
    return env


class ProviderCliTool(BaseTool):
    """Shell out to cursor/grok/opencode (or a fake) inside the worktree."""

    name: str = "run_agent_cli"
    description: str = "Run the configured agent CLI once in the worktree, then stop."
    command: list[str] = Field(default_factory=list)
    workdir: str = ""
    log_path: str = ""
    _on_pid: Callable[[int], None] | None = PrivateAttr(default=None)
    _on_pid_done: Callable[[int], None] | None = PrivateAttr(default=None)
    last_returncode: int = 0

    def set_pid_hooks(
        self,
        on_start: Callable[[int], None] | None,
        on_done: Callable[[int], None] | None,
    ) -> None:
        self._on_pid = on_start
        self._on_pid_done = on_done

    def _run(self) -> str:
        if not self.command:
            raise ValueError("ProviderCliTool.command is empty")
        workdir = Path(self.workdir)
        log_path = Path(self.log_path) if self.log_path else None
        logger.info("running %s in %s", self.command, workdir)
        with subprocess.Popen(
            self.command,
            cwd=str(workdir),
            env=provider_cli_env(workdir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        ) as proc:
            if self._on_pid:
                self._on_pid(proc.pid)
            assert proc.stdout is not None
            lines: list[str] = []
            try:
                for line in proc.stdout:
                    lines.append(line)
                    if log_path is not None:
                        with log_path.open("a", encoding="utf-8") as fh:
                            fh.write(line)
            finally:
                proc.wait()
                if self._on_pid_done:
                    self._on_pid_done(proc.pid)
            self.last_returncode = proc.returncode or 0
            output = "".join(lines)
            if self.last_returncode != 0:
                raise RuntimeError(f"agent CLI exited {self.last_returncode}: {output[-2000:]}")
            return output or "ok"


def run_provider_command(
    command: list[str],
    *,
    workdir: Path,
    log_path: Path,
    on_pid: Callable[[int], None] | None = None,
    on_pid_done: Callable[[int], None] | None = None,
) -> int:
    """Run provider CLI and tee output to log_path. Returns exit code."""
    tool = ProviderCliTool(
        command=command,
        workdir=str(workdir),
        log_path=str(log_path),
    )
    tool.set_pid_hooks(on_pid, on_pid_done)
    try:
        tool._run()
        return 0
    except RuntimeError:
        return tool.last_returncode or 1
