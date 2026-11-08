"""Parallel per-slot loops with gates, issue claims, worktrees, cooldowns, and cron schedules."""

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
    ScheduleConfig,
    is_composite,
    resolved_cooldown_seconds,
    resolved_gate_backoff_initial_seconds,
    resolved_gate_backoff_max_seconds,
)
from agent_orc.crew.factory import run_skill_once
from agent_orc.gate import gate_passes, next_gate_backoff
from agent_orc.schedule import cron_matches, local_now, minute_floor, scheduled_agent_names
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

    Agents named under any ``schedules:`` entry are schedule-only: they fire once
    per due cron tick (skip missed ticks while a run is in progress) instead of
    looping on cooldown.

    count=None means daemon (forever). count=N means each recurring slot runs N
    times and each schedule slot completes N successful fires (gate misses and
    claim misses do not count). For composites, one run / fire is one full chain
    pass.
    """
    ctl = shutdown or ShutdownController()
    root = (repo_root or Path(config.orchestrator.repo_root)).resolve()
    worktrees_dir = (root / config.orchestrator.worktrees_dir).resolve()
    logs_dir = (root / config.orchestrator.logs_dir).resolve()
    logs_dir.mkdir(parents=True, exist_ok=True)
    worktrees_dir.mkdir(parents=True, exist_ok=True)
    ownership = IssueOwnership()

    scheduled_names = scheduled_agent_names(config)
    selected_by_name = {a.name: a for a in agents}
    recurring = [a for a in agents if a.name not in scheduled_names]
    recurring_slots = _expand_slots(recurring)

    tasks: list[asyncio.Task[int]] = [
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
        for index, (agent, parallel_id) in enumerate(recurring_slots)
    ]

    schedule_meta: list[tuple[ScheduleConfig, AgentConfig, int]] = []
    for schedule in config.schedules.values():
        for agent_name in schedule.agents:
            agent = selected_by_name.get(agent_name)
            if agent is None:
                continue
            for parallel_id in range(1, agent.parallel_run + 1):
                schedule_meta.append((schedule, agent, parallel_id))

    base_index = len(recurring_slots)
    for offset, (schedule, agent, parallel_id) in enumerate(schedule_meta):
        tasks.append(
            asyncio.create_task(
                _schedule_loop(
                    config,
                    schedule,
                    agent,
                    parallel_id=parallel_id,
                    index=base_index + offset,
                    count=count,
                    shutdown=ctl,
                    repo_root=root,
                    worktrees_dir=worktrees_dir,
                    logs_dir=logs_dir,
                    ownership=ownership,
                ),
                name=f"schedule:{schedule.name}:{agent.name}#{parallel_id}",
            )
        )

    if not tasks:
        logger.error("no agent slots to run")
        return 1

    results = await asyncio.gather(*tasks, return_exceptions=True)
    exit_code = 0
    labels = [t.get_name() for t in tasks]
    for label, result in zip(labels, results, strict=True):
        if isinstance(result, Exception):
            logger.error("%s failed: %s", label, result)
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

    if is_composite(agent):
        return await _chain_loop(
            config,
            agent,
            parallel_id=parallel_id,
            count=count,
            shutdown=shutdown,
            repo_root=repo_root,
            worktrees_dir=worktrees_dir,
            logs_dir=logs_dir,
            ownership=ownership,
        )

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

        fired = await _leaf_attempt(
            config,
            agent,
            parallel_id=parallel_id,
            owner=owner,
            ownership=ownership,
            shutdown=shutdown,
            repo_root=repo_root,
            worktrees_dir=worktrees_dir,
            logs_dir=logs_dir,
            worktree_key=f"{agent.name}-{parallel_id}",
        )
        if not fired:
            await miss("gate or claim miss")
            continue

        consecutive_misses = 0
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


async def _chain_loop(
    config: AppConfig,
    agent: AgentConfig,
    *,
    parallel_id: int,
    count: int | None,
    shutdown: ShutdownController,
    repo_root: Path,
    worktrees_dir: Path,
    logs_dir: Path,
    ownership: IssueOwnership,
) -> int:
    orch = config.orchestrator
    runs_done = 0
    consecutive_misses = 0
    logger.info(
        "chain loop started: %s slot %s (%s steps, count=%s)",
        agent.name,
        parallel_id,
        len(agent.chain or []),
        count,
    )

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
                "chain loop finished: %s slot %s (%s passes)",
                agent.name,
                parallel_id,
                runs_done,
            )
            return 0

        fired = await _chain_attempt(
            config,
            agent,
            parallel_id=parallel_id,
            ownership=ownership,
            shutdown=shutdown,
            repo_root=repo_root,
            worktrees_dir=worktrees_dir,
            logs_dir=logs_dir,
        )
        if not fired:
            await miss("gate miss")
            continue

        consecutive_misses = 0
        cooldown = resolved_cooldown_seconds(agent, orch)
        if cooldown > 0:
            await _sleep_interruptible(cooldown, shutdown)

        runs_done += 1
        if count is not None and runs_done >= count:
            logger.info(
                "chain loop finished: %s slot %s (%s passes)",
                agent.name,
                parallel_id,
                runs_done,
            )
            return 0


async def _schedule_loop(
    config: AppConfig,
    schedule: ScheduleConfig,
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

    fires_done = 0
    last_fired_minute = None
    # Claim owners are agent-scoped so the same agent in multiple schedules shares the map.
    owner = f"{agent.name}#{parallel_id}"
    poll = orch.schedule_poll_seconds
    logger.info(
        "schedule loop started: %s agent %s slot %s cron=%r (count=%s)",
        schedule.name,
        agent.name,
        parallel_id,
        schedule.cron,
        count,
    )

    while True:
        if shutdown.shutting_down:
            return 0
        if count is not None and fires_done >= count:
            logger.info(
                "schedule loop finished: %s agent %s slot %s (%s fires)",
                schedule.name,
                agent.name,
                parallel_id,
                fires_done,
            )
            return 0

        now = local_now()
        floored = minute_floor(now)
        due = cron_matches(schedule.cron, floored) and floored != last_fired_minute
        if due:
            # Consume the tick before work so overrun skips intervening fires.
            last_fired_minute = floored
            logger.info(
                "schedule %s due for %s slot %s at %s",
                schedule.name,
                agent.name,
                parallel_id,
                floored.isoformat(timespec="minutes"),
            )
            if is_composite(agent):
                fired = await _chain_attempt(
                    config,
                    agent,
                    parallel_id=parallel_id,
                    ownership=ownership,
                    shutdown=shutdown,
                    repo_root=repo_root,
                    worktrees_dir=worktrees_dir,
                    logs_dir=logs_dir,
                    apply_step_cooldowns=False,
                )
            else:
                fired = await _leaf_attempt(
                    config,
                    agent,
                    parallel_id=parallel_id,
                    owner=owner,
                    ownership=ownership,
                    shutdown=shutdown,
                    repo_root=repo_root,
                    worktrees_dir=worktrees_dir,
                    logs_dir=logs_dir,
                    worktree_key=f"{schedule.name}-{agent.name}-{parallel_id}",
                )
            if fired:
                fires_done += 1
                if count is not None and fires_done >= count:
                    logger.info(
                        "schedule loop finished: %s agent %s slot %s (%s fires)",
                        schedule.name,
                        agent.name,
                        parallel_id,
                        fires_done,
                    )
                    return 0
            else:
                logger.info(
                    "schedule %s agent %s slot %s tick miss (gate/claim); waiting for next cron",
                    schedule.name,
                    agent.name,
                    parallel_id,
                )

        await _sleep_interruptible(poll if poll > 0 else 0.2, shutdown)


async def _leaf_attempt(
    config: AppConfig,
    agent: AgentConfig,
    *,
    parallel_id: int,
    owner: str,
    ownership: IssueOwnership,
    shutdown: ShutdownController,
    repo_root: Path,
    worktrees_dir: Path,
    logs_dir: Path,
    worktree_key: str,
) -> bool:
    """Gate → optional claim → run. Returns True when a run was started."""
    passed = await asyncio.to_thread(gate_passes, agent, cwd=repo_root)
    if not passed:
        return False

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
            return False
        claimed = await ownership.claim(owner, numbers)
        if claimed is None:
            return False
        issue_label = str(claimed)

    await _execute_run(
        config,
        agent,
        parallel_id=parallel_id,
        issue_label=issue_label,
        claimed=claimed,
        owner=owner,
        ownership=ownership,
        shutdown=shutdown,
        repo_root=repo_root,
        worktrees_dir=worktrees_dir,
        logs_dir=logs_dir,
        worktree_key=worktree_key,
    )
    return True


async def _chain_attempt(
    config: AppConfig,
    agent: AgentConfig,
    *,
    parallel_id: int,
    ownership: IssueOwnership,
    shutdown: ShutdownController,
    repo_root: Path,
    worktrees_dir: Path,
    logs_dir: Path,
    apply_step_cooldowns: bool = True,
) -> bool:
    """
    Composite gate → ordered steps. Returns True when the composite gate passed
    (one chain pass completed, including all-step skips).
    """
    orch = config.orchestrator
    steps = agent.chain or []
    passed = await asyncio.to_thread(gate_passes, agent, cwd=repo_root)
    if not passed:
        return False

    for step_index, step in enumerate(steps):
        if shutdown.shutting_down:
            return True

        step_passed = await asyncio.to_thread(gate_passes, step, cwd=repo_root)
        if not step_passed:
            logger.info(
                "%s slot %s step %s gate miss; skipping",
                agent.name,
                parallel_id,
                step.name,
            )
            continue

        issue_label = UNASSIGNED_ISSUE
        claimed: int | None = None
        owner = f"{step.name}#{parallel_id}"
        if step.issues is not None:
            try:
                numbers = await asyncio.to_thread(
                    list_issue_numbers, step.issues.command, cwd=repo_root
                )
            except IssueListError as exc:
                logger.info(
                    "%s slot %s step %s issue list failed: %s; skipping",
                    agent.name,
                    parallel_id,
                    step.name,
                    exc,
                )
                continue
            claimed = await ownership.claim(owner, numbers)
            if claimed is None:
                logger.info(
                    "%s slot %s step %s claim miss; skipping",
                    agent.name,
                    parallel_id,
                    step.name,
                )
                continue
            issue_label = str(claimed)

        safe_step = step.name.replace(":", "-").replace("/", "-")
        await _execute_run(
            config,
            step,
            parallel_id=parallel_id,
            issue_label=issue_label,
            claimed=claimed,
            owner=owner,
            ownership=ownership,
            shutdown=shutdown,
            repo_root=repo_root,
            worktrees_dir=worktrees_dir,
            logs_dir=logs_dir,
            worktree_key=f"{agent.name}-{parallel_id}-s{step_index + 1}-{safe_step}",
        )

        if apply_step_cooldowns:
            step_cooldown = resolved_cooldown_seconds(step, orch)
            if step_cooldown > 0:
                await _sleep_interruptible(step_cooldown, shutdown)

    return True


async def _execute_run(
    config: AppConfig,
    agent: AgentConfig,
    *,
    parallel_id: int,
    issue_label: str,
    claimed: int | None,
    owner: str,
    ownership: IssueOwnership,
    shutdown: ShutdownController,
    repo_root: Path,
    worktrees_dir: Path,
    logs_dir: Path,
    worktree_key: str,
) -> None:
    orch = config.orchestrator
    session: WorktreeSession | None = None
    try:
        if orch.pull_before_run:
            await asyncio.to_thread(pull_repo, repo_root, orch.default_branch)
        session = await asyncio.to_thread(
            create_worktree,
            repo_root,
            worktrees_dir,
            worktree_key,
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
            prompt=render_agent_prompt(agent.prompt, parallel_id=parallel_id, issue=issue_label),
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


async def _sleep_interruptible(seconds: float, shutdown: ShutdownController) -> None:
    if seconds <= 0:
        return
    end = asyncio.get_event_loop().time() + seconds
    while asyncio.get_event_loop().time() < end:
        if shutdown.shutting_down:
            return
        await asyncio.sleep(min(0.2, end - asyncio.get_event_loop().time()))
