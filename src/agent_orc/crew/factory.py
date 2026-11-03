"""Build a light CrewAI Agent/Task/Crew and execute the provider CLI tool."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from crewai import Agent, Crew, Process, Task

from agent_orc.assignment import UNASSIGNED_ISSUE
from agent_orc.config import AgentConfig, AppConfig
from agent_orc.crew.tools import ProviderCliTool, run_provider_command
from agent_orc.logging_setup import agent_run_log_path
from agent_orc.messaging import publish
from agent_orc.providers import render_command
from agent_orc.providers.opencode import bind_session, delete_session

logger = logging.getLogger("agent_orc.crew")


def build_crew(
    agent_cfg: AgentConfig,
    config: AppConfig,
    *,
    workdir: Path,
    log_path: Path,
) -> tuple[Crew, ProviderCliTool, str | None]:
    template = config.providers[agent_cfg.provider]
    command = render_command(
        template,
        prompt=agent_cfg.prompt,
        workdir=str(workdir),
        skill=agent_cfg.skill,
    )
    command, session_id = bind_session(command)
    tool = ProviderCliTool(
        command=command,
        workdir=str(workdir),
        log_path=str(log_path),
    )
    agent = Agent(
        role=f"{agent_cfg.name} runner",
        goal=f"Execute the {agent_cfg.skill} skill once via the CLI tool",
        backstory="Orchestrated unattended skill runner for agent-orc.",
        tools=[tool],
        verbose=False,
        allow_delegation=False,
    )
    task = Task(
        description=(
            f"Call the run_agent_cli tool exactly once, then finish. Skill: {agent_cfg.skill}."
        ),
        expected_output="CLI exit success",
        agent=agent,
        tools=[tool],
    )
    crew = Crew(
        agents=[agent],
        tasks=[task],
        process=Process.sequential,
        verbose=False,
    )
    return crew, tool, session_id


def run_skill_once(
    agent_cfg: AgentConfig,
    config: AppConfig,
    *,
    workdir: Path,
    logs_dir: Path,
    on_pid: Callable[[int], None] | None = None,
    on_pid_done: Callable[[int], None] | None = None,
    on_opencode_session: Callable[[str], None] | None = None,
    on_opencode_session_done: Callable[[str], None] | None = None,
    use_crew_kickoff: bool = False,
    parallel_id: int = 1,
    issue: str = UNASSIGNED_ISSUE,
) -> int:
    """
    Construct CrewAI objects, then run the provider CLI.

    By default invokes the tool directly (no LLM required). Set
    use_crew_kickoff=True to call crew.kickoff() instead.

    For OpenCode providers, binds a session id via `--session` and deletes it
    with `opencode session delete` when the run ends (so a restarted server
    will not respawn a killed session).
    """
    log_path = agent_run_log_path(logs_dir, agent_cfg.name, parallel_id)
    log_path.write_text("", encoding="utf-8")
    crew, tool, session_id = build_crew(agent_cfg, config, workdir=workdir, log_path=log_path)
    publish(
        "skill.start",
        {
            "agent": agent_cfg.name,
            "parallel_id": parallel_id,
            "issue": issue,
            "workdir": str(workdir),
            "opencode_session": session_id,
        },
    )
    tool.set_pid_hooks(on_pid, on_pid_done)
    if session_id is not None and on_opencode_session is not None:
        on_opencode_session(session_id)

    code = 1
    try:
        if use_crew_kickoff:
            try:
                crew.kickoff()
                code = tool.last_returncode
            except Exception:
                logger.exception("crew.kickoff failed for %s", agent_cfg.name)
                code = tool.last_returncode or 1
        else:
            code = run_provider_command(
                tool.command,
                workdir=workdir,
                log_path=log_path,
                on_pid=on_pid,
                on_pid_done=on_pid_done,
            )
    finally:
        if session_id is not None:
            binary = tool.command[0] if tool.command else "opencode"
            delete_session(session_id, cwd=workdir, binary=binary)
            if on_opencode_session_done is not None:
                on_opencode_session_done(session_id)

    publish(
        "skill.end",
        {
            "agent": agent_cfg.name,
            "parallel_id": parallel_id,
            "issue": issue,
            "exit_code": code,
            "log": str(log_path),
            "opencode_session": session_id,
        },
    )
    return code
