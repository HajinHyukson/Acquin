"""Daily EOD pipeline orchestrator (context doc §5, Phase 5).

Chains the daily steps — ingest → features → validate → predict — capturing
per-step status and errors so a failure in one step is visible and recoverable
rather than aborting the whole run silently. Each step is retried a few times
before being recorded as failed.
"""

from __future__ import annotations

import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from kospi_flow.analytics.pipeline import generate_features
from kospi_flow.core.config import Settings, get_settings
from kospi_flow.core.db import Database, get_database
from kospi_flow.core.enums import FreshnessState
from kospi_flow.core.logging import get_logger
from kospi_flow.data.ingestion import build_ingestor
from kospi_flow.data.validation import DataValidator

logger = get_logger(__name__)


def retry(
    fn: Callable[[], Any], attempts: int = 3, delay: float = 0.0
) -> Any:
    """Call ``fn``; retry on exception up to ``attempts`` times."""
    last: Exception | None = None
    for i in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - orchestration boundary
            last = exc
            logger.warning("Attempt %d/%d failed: %s", i, attempts, exc)
            if i < attempts and delay:
                time.sleep(delay)
    assert last is not None
    raise last


@dataclass
class StepResult:
    name: str
    status: str  # "ok" | "error" | "skipped"
    detail: str | None = None
    error: str | None = None


@dataclass
class PipelineReport:
    steps: list[StepResult] = field(default_factory=list)

    def add(self, name: str, status: str, detail: str | None = None, error: str | None = None) -> None:
        self.steps.append(StepResult(name, status, detail, error))

    @property
    def ok(self) -> bool:
        return all(s.status != "error" for s in self.steps)

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "steps": [s.__dict__ for s in self.steps],
        }


def _run_step(
    report: PipelineReport, name: str, fn: Callable[[], Any], attempts: int = 3
) -> Any:
    try:
        result = retry(fn, attempts=attempts)
        detail = str(result) if not isinstance(result, (dict, list)) else None
        report.add(name, "ok", detail=detail)
        return result
    except Exception as exc:  # noqa: BLE001
        logger.error("Step '%s' failed: %s", name, exc)
        report.add(name, "error", error=f"{type(exc).__name__}: {exc}")
        logger.debug(traceback.format_exc())
        return None


def run_daily_pipeline(
    start: date,
    end: date,
    tickers: list[str] | None = None,
    horizons: tuple[int, ...] = (5,),
    train: bool = False,
    freshness_state: FreshnessState = FreshnessState.FINAL_EOD,
    database: Database | None = None,
    settings: Settings | None = None,
) -> PipelineReport:
    """Run the full daily pipeline for ``[start, end]``.

    Steps after a failed step still run where they don't depend on it, so the
    report shows exactly which stage broke. Set ``train=True`` to (re)train
    models before inference (otherwise inference uses the saved bundle).
    """
    settings = settings or get_settings()
    database = database or get_database(settings)
    report = PipelineReport()

    database.create_all()

    ingestor = build_ingestor(
        settings=settings, database=database, freshness_state=freshness_state
    )
    _run_step(
        report,
        "ingest",
        lambda: ingestor.run(start, end, tickers=tickers).summary(),
    )
    _run_step(report, "features", lambda: f"rows={generate_features(database, tickers)}")

    for h in horizons:
        model_name = f"gbm_return_{h}d"
        if train:
            from kospi_flow.ml.train import train_and_evaluate

            _run_step(
                report,
                f"train_{h}d",
                lambda h=h: f"backend={train_and_evaluate(database, horizon=h, tickers=tickers, settings=settings).backend}",
            )

        from kospi_flow.ml.inference import load_bundle, predict_and_store

        _run_step(
            report,
            f"predict_{h}d",
            lambda mn=model_name: f"stored={predict_and_store(database, mn, tickers=tickers, settings=settings)}",
        )

        # Model-drift monitoring + retrain decision (best-effort; skipped if no
        # bundle exists yet). When a retrain is warranted (drift alert or age
        # cap) the step either retrains-then-predicts (if KOSPI_RETRAIN_ON_DRIFT)
        # or just records "retrain_recommended" — the RETRAIN_RECOMMENDED alert
        # then reaches the notifier in the alerts step (§24.2 / §25 Phase C).
        from kospi_flow.ml.drift import compute_drift
        from kospi_flow.ml.lifecycle import days_since, decide_retrain

        def _drift_and_maybe_retrain(mn=model_name, h=h):
            bundle = load_bundle(mn, settings)
            status = compute_drift(database, bundle, settings=settings)["status"]
            decision = decide_retrain(
                drift_status=status,
                age_days=days_since(bundle.get("trained_at"), end),
                max_model_age_days=settings.max_model_age_days,
            )
            if not decision.should_retrain:
                return f"status={status}"
            why = "; ".join(decision.reasons)
            if settings.retrain_on_drift:
                from kospi_flow.ml.train import train_and_evaluate

                train_and_evaluate(
                    database, horizon=h, tickers=tickers, settings=settings
                )
                predict_and_store(database, mn, tickers=tickers, settings=settings)
                return f"status={status} retrained ({why})"
            return f"status={status} retrain_recommended ({why})"

        _run_step(report, f"drift_{h}d", _drift_and_maybe_retrain)

    validator = DataValidator(database)
    rep = _run_step(report, "validate", lambda: validator.validate(tickers))
    if rep is not None and not rep.ok:
        # Validation errors are surfaced but don't crash the pipeline.
        report.add(
            "validate_summary", "error", error=f"{len(rep.errors)} validation error(s)"
        )

    # Evaluate alert rules and dispatch through the configured notifier.
    from kospi_flow.alerts import evaluate_alerts, get_notifier

    def _alerts() -> str:
        alerts = evaluate_alerts(database, validation_report=rep, settings=settings)
        notifier = get_notifier(settings)
        sent = notifier.send_many(alerts)
        return f"triggered={len(alerts)} sent={sent}"

    _run_step(report, "alerts", _alerts)

    logger.info("Daily pipeline finished: ok=%s", report.ok)
    return report
