"""Cron schedule helpers (configured IANA timezone, minute resolution)."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from croniter import croniter

from agent_orc.config import DEFAULT_SCHEDULE_TIMEZONE, AppConfig, ScheduleConfig


def schedule_now(timezone: str = DEFAULT_SCHEDULE_TIMEZONE) -> datetime:
    """Wall clock in the orchestrator's configured IANA timezone."""
    return datetime.now(ZoneInfo(timezone))


def cron_matches(expr: str, when: datetime) -> bool:
    """True if `when` floored to the minute is a fire time for the 5-field cron."""
    floored = when.replace(second=0, microsecond=0)
    return bool(croniter.match(expr, floored))


def minute_floor(when: datetime) -> datetime:
    return when.replace(second=0, microsecond=0)


def scheduled_agent_names(config: AppConfig) -> set[str]:
    names: set[str] = set()
    for schedule in config.schedules.values():
        names.update(schedule.agents)
    return names


def schedules_for_agent(config: AppConfig, agent_name: str) -> list[ScheduleConfig]:
    return [s for s in config.schedules.values() if agent_name in s.agents]
