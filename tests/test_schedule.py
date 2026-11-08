from __future__ import annotations

from datetime import UTC, datetime

from agent_orc.config import AppConfig, OrchestratorConfig, ScheduleConfig
from agent_orc.schedule import cron_matches, minute_floor, scheduled_agent_names


def test_cron_matches_floors_to_minute() -> None:
    when = datetime(2026, 11, 8, 9, 0, 45, tzinfo=UTC)
    assert cron_matches("0 * * * *", when) is True
    assert cron_matches("0 * * * *", when.replace(minute=1)) is False
    assert cron_matches("* * * * *", when) is True


def test_minute_floor() -> None:
    when = datetime(2026, 11, 8, 9, 7, 12, 345678, tzinfo=UTC)
    assert minute_floor(when) == when.replace(second=0, microsecond=0)


def test_scheduled_agent_names() -> None:
    cfg = AppConfig(
        orchestrator=OrchestratorConfig(),
        providers={},
        agents={},
        schedules={
            "a": ScheduleConfig(name="a", cron="0 * * * *", agents=["planner", "x"]),
            "b": ScheduleConfig(name="b", cron="0 8 * * *", agents=["planner"]),
        },
    )
    assert scheduled_agent_names(cfg) == {"planner", "x"}
