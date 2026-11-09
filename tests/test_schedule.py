from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from agent_orc.config import AppConfig, OrchestratorConfig, ScheduleConfig
from agent_orc.schedule import (
    cron_matches,
    minute_floor,
    schedule_now,
    scheduled_agent_names,
)


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


def test_schedule_now_uses_iana_zone() -> None:
    now = schedule_now("Asia/Hong_Kong")
    assert now.tzinfo is not None
    assert now.tzinfo.key == "Asia/Hong_Kong"  # type: ignore[union-attr]


def test_cron_matches_in_hong_kong_wall_time() -> None:
    # 00:00 UTC == 08:00 HKT → morning cron fires; same instant in UTC hour fields would not.
    hkt = datetime(2026, 11, 9, 8, 0, 0, tzinfo=ZoneInfo("Asia/Hong_Kong"))
    utc = hkt.astimezone(UTC)
    assert cron_matches("0 8,12,18 * * *", hkt) is True
    assert cron_matches("0 8,12,18 * * *", utc) is False
    assert utc.hour == 0
