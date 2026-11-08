"""Parallel per-slot loops with gates, issue claims, worktrees, and cooldowns."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from pathlib import Path

from agent_orc.assignment import (
    UNASSIGNED_ISSUE,
    IssueListError,
    IssueOwnership,
    list_issue_numbers,
    render_agent_prompt,
)
from agent_orc.config import (
    AgentConfig,
    AppConfig,
    resolved_cooldown_seconds,
    resolved_gate_backoff_initial_seconds,
    resolved_gate_backoff_max_seconds,
)
from agent_orc.crew.factory import run_skill_once
from agent_orc.gate import gate_passes, next_gate_backoff
from agent_orc.shutdown import OpenCodeSessionRef, ShutdownController
from agent_orc.worktree import (
    WorktreeSession,
    create_worktree,
    delete_worktree,
    pull_repo,
)

logger = logging.getLogger("agent_orc.supervisor")


async def run_supervisor(
    config: AppConfig,
    agents: list[AgentConfig],
    *,
    count: int | None = None,
    shutdown: ShutdownController | None = None,
    repo_root: Path | None = None,
) -> int:
    """
    Run one loop per parallel slot. Slots of every agent share one issue map.

    count=None means daemon (forever). count=N means each slot runs N times
    (gate misses and claim misses do not count).
    """
    ctl = shutdown or ShutdownController()
    root = (repo_root or Path(config.orchestrator.repo_root)).resolve()
    worktrees_dir = (root / config.orchestrator.worktrees_dir).resolve()
    logs_dir = (root / config.orchestrator.logs_dir).resolve()
    logs_dir.mkdir(parents=True, exist_ok=True)
    worktrees_dir.mkdir(parents=True, exist_ok=True)
    ownership = IssueOwnership()
    slots = _expand_slots(agents)

    tasks = [
        asyncio.create_task(
            _skill_loop(
                config,
                agent,
                parallel_id=parallel_id,
                index=index,
                count=count,
                shutdown=ctl,
                repo_root=root,
                worktrees_dir=worktrees_dir,
                logs_dir=logs_dir,
                ownership=ownership,
            ),
            name=f"skill:{agent.name}#{parallel_id}",
        )
        for index, (agent, parallel_id) in enumerate(slots)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    exit_code = 0
    for (agent, parallel_id), result in zip(slots, results, strict=True):
        if isinstance(result, Exception):
            logger.error("skill loop %s slot %s failed: %s", agent.name, parallel_id, result)
            exit_code = 1
        elif isinstance(result, int) and result != 0:
            exit_code = result
    return exit_code


def _expand_slots(agents: list[AgentConfig]) -> list[tuple[AgentConfig, int]]:
    slots: list[tuple[AgentConfig, int]] = []
    for agent in agents:
        for parallel_id in range(1, agent.parallel_run + 1):
            slots.append((agent, parallel_id))
    return slots


async def _skill_loop(
    config: AppConfig,
    agent: AgentConfig,
    *,
    parallel_id: int,
    index: int,
    count: int | None,
    shutdown: ShutdownController,
    repo_root: Path,
    worktrees_dir: Path,
    logs_dir: Path,
    ownership: IssueOwnership,
) -> int:
    orch = config.orchestrator
    if index > 0 and orch.stagger_seconds > 0:
        await asyncio.sleep(orch.stagger_seconds * index)

    runs_done = 0
    consecutive_misses = 0
    owner = f"{agent.name}#{parallel_id}"
    logger.info("skill loop started: %s slot %s (count=%s)", agent.name, parallel_id, count)

    async def miss(reason: str) -> None:
        nonlocal consecutive_misses
        consecutive_misses += 1
        delay = next_gate_backoff(
            0.0,
            initial=resolved_gate_backoff_initial_seconds(agent, orch),
            maximum=resolved_gate_backoff_max_seconds(agent, orch),
            consecutive_misses=consecutive_misses,
        )
        logger.info(
            "%s slot %s %s #%s; sleeping %.1fs",
            agent.name,
            parallel_id,
            reason,
            consecutive_misses,
            delay,
        )
        await _sleep_interruptible(delay, shutdown)

    while True:
        if shutdown.shutting_down:
            return 0
        if count is not None and runs_done >= count:
            logger.info(
                "skill loop finished: %s slot %s (%s runs)",
                agent.name,
                parallel_id,
                runs_done,
            )
            return 0

        passed = await asyncio.to_thread(gate_passes, agent, cwd=repo_root)
        if not passed:
            await miss("gate miss")
            continue

        issue_label = UNASSIGNED_ISSUE
        claimed: int | None = None
        if agent.parallel_run > 1 and agent.issues is not None:
            try:
                numbers = await asyncio.to_thread(
                    list_issue_numbers, agent.issues.command, cwd=repo_root
                )
            except IssueListError as exc:
                logger.info(
                    "%s slot %s issue list failed: %s",
                    agent.name,
                    parallel_id,
                    exc,
                )
                await miss("claim miss")
                continue
            claimed = await ownership.claim(owner, numbers)
            if claimed is None:
                await miss("claim miss")
                continue
            issue_label = str(claimed)

        consecutive_misses = 0
        session: WorktreeSession | None = None
        try:
            if orch.pull_before_run:
                await asyncio.to_thread(pull_repo, repo_root, orch.default_branch)
            session = await asyncio.to_thread(
                create_worktree,
                repo_root,
                worktrees_dir,
                f"{agent.name}-{parallel_id}",
                base_branch=orch.default_branch,
            )
            shutdown.register_worktree(session)
            wt_session = session

            def on_pid(pid: int) -> None:
                shutdown.register_pid(pid)

            def on_pid_done(pid: int) -> None:
                shutdown.unregister_pid(pid)

            def on_opencode_session(session_id: str, *, wt: WorktreeSession = wt_session) -> None:
                binary = "opencode"
                template = config.providers.get(agent.provider) or []
                if template:
                    binary = template[0]
                shutdown.register_opencode_session(
                    OpenCodeSessionRef(
                        session_id=session_id,
                        cwd=wt.path,
                        binary=binary,
                    )
                )

            def on_opencode_session_done(session_id: str) -> None:
                shutdown.unregister_opencode_session(session_id)

            running = replace(
                agent,
                prompt=render_agent_prompt(
                    agent.prompt, parallel_id=parallel_id, issue=issue_label
                ),
            )
            code = await asyncio.to_thread(
                run_skill_once,
                running,
                config,
                workdir=session.path,
                logs_dir=logs_dir,
                repo_root=repo_root,
                on_pid=on_pid,
                on_pid_done=on_pid_done,
                on_opencode_session=on_opencode_session,
                on_opencode_session_done=on_opencode_session_done,
                parallel_id=parallel_id,
                issue=issue_label,
            )
            if code != 0:
                logger.error("%s slot %s run exited %s", agent.name, parallel_id, code)
            else:
                logger.info("%s slot %s run completed ok", agent.name, parallel_id)
        except Exception:
            logger.exception("%s slot %s run failed", agent.name, parallel_id)
        finally:
            try:
                if claimed is not None:
                    await ownership.release(owner)
            finally:
                if session is not None:
                    await asyncio.to_thread(delete_worktree, session)
                    shutdown.unregister_worktree(session)

        runs_done += 1
        if count is not None and runs_done >= count:
            logger.info(
                "skill loop finished: %s slot %s (%s runs)",
                agent.name,
                parallel_id,
                runs_done,
            )
            return 0

        cooldown = resolved_cooldown_seconds(agent, orch)
        if cooldown > 0:
            await _sleep_interruptible(cooldown, shutdown)


async def _sleep_interruptible(seconds: float, shutdown: ShutdownController) -> None:
    if seconds <= 0:
        return
    end = asyncio.get_event_loop().time() + seconds
    while asyncio.get_event_loop().time() < end:
        if shutdown.shutting_down:
            return
        await asyncio.sleep(min(0.2, end - asyncio.get_event_loop().time()))
