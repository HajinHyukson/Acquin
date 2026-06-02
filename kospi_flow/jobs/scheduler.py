"""Lightweight KST job scheduler (Phase 5, context doc §5).

Maps the recommended post-close timetable to pipeline jobs without pulling in a
heavyweight orchestrator. Use ``serve()`` for a simple always-on process, or
generate a crontab (see ``infra/cron/kospi-flow.cron``) to drive the same jobs
from cron / a cloud scheduler. The pure ``due_entries`` function is unit-tested.

For production-grade retries, backfills, and dependency graphs, migrate these
job definitions to Airflow or Prefect.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from kospi_flow.core.config import Settings, get_settings
from kospi_flow.core.db import Database, get_database
from kospi_flow.core.enums import FreshnessState
from kospi_flow.core.logging import get_logger
from kospi_flow.jobs.daily import PipelineReport, run_daily_pipeline

logger = get_logger(__name__)


@dataclass(frozen=True)
class ScheduleEntry:
    time_kst: str  # "HH:MM"
    job: str
    freshness: FreshnessState
    predict: bool
    description: str


#: Default daily timetable (Korea time), per context doc §5.
DEFAULT_SCHEDULE: tuple[ScheduleEntry, ...] = (
    ScheduleEntry("15:50", "preliminary", FreshnessState.PRELIMINARY, False,
                  "Preliminary OHLCV after the close."),
    ScheduleEntry("16:30", "first_eod", FreshnessState.FIRST_EOD, False,
                  "First-pass EOD prices/flows."),
    ScheduleEntry("18:30", "final_eod", FreshnessState.FINAL_EOD, True,
                  "Final reconciled flows + features + ML inference."),
)


def due_entries(
    now_hm: str, schedule: tuple[ScheduleEntry, ...] = DEFAULT_SCHEDULE
) -> list[ScheduleEntry]:
    """Entries whose scheduled time matches ``now_hm`` ('HH:MM')."""
    return [e for e in schedule if e.time_kst == now_hm]


def run_entry(
    entry: ScheduleEntry,
    database: Database | None = None,
    settings: Settings | None = None,
    lookback_days: int = 120,
    today: date | None = None,
) -> PipelineReport:
    """Run one schedule entry as a daily-pipeline invocation."""
    settings = settings or get_settings()
    database = database or get_database(settings)
    today = today or datetime.now(ZoneInfo(settings.timezone)).date()
    start = today - timedelta(days=lookback_days)
    logger.info("Running scheduled job '%s' for %s..%s", entry.job, start, today)
    return run_daily_pipeline(
        start=start,
        end=today,
        horizons=(5,) if entry.predict else (),
        train=False,
        freshness_state=entry.freshness,
        database=database,
        settings=settings,
    )


def serve(
    schedule: tuple[ScheduleEntry, ...] = DEFAULT_SCHEDULE,
    settings: Settings | None = None,
    poll_seconds: int = 60,
    now_provider: Callable[[], datetime] | None = None,
    max_ticks: int | None = None,
) -> None:
    """Blocking loop: each minute, run any entries due at the current KST minute.

    ``now_provider`` and ``max_ticks`` exist for testing; in production call with
    defaults to run forever.
    """
    settings = settings or get_settings()
    tz = ZoneInfo(settings.timezone)
    now_provider = now_provider or (lambda: datetime.now(tz))
    database = get_database(settings)
    last_run_minute: str | None = None
    ticks = 0
    logger.info("Scheduler started (%d entries).", len(schedule))
    while True:
        now = now_provider()
        hm = now.strftime("%H:%M")
        if hm != last_run_minute:
            for entry in due_entries(hm, schedule):
                try:
                    run_entry(entry, database=database, settings=settings)
                except Exception as exc:  # noqa: BLE001
                    logger.error("Scheduled job '%s' failed: %s", entry.job, exc)
            last_run_minute = hm
        ticks += 1
        if max_ticks is not None and ticks >= max_ticks:
            return
        time.sleep(poll_seconds)
