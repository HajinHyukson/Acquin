"""Retrain-trigger policy (context doc §24.2 / §25 Phase C).

Pure, dependency-light decision logic so it is easy to test: given the latest
feature-drift status and the active bundle's age, decide whether a retrain is
warranted. The daily pipeline either acts on it (when ``retrain_on_drift`` is
set) or emits a ``RETRAIN_RECOMMENDED`` alert and leaves the retrain to CI/local.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass
class RetrainDecision:
    should_retrain: bool
    reasons: list[str]


def days_since(trained_at: str | None, today: date) -> int | None:
    """Whole days between an ISO ``trained_at`` timestamp and ``today``.

    Returns ``None`` when ``trained_at`` is missing or unparseable, so a bundle
    with no/garbage timestamp never triggers the age rule.
    """
    if not trained_at:
        return None
    try:
        stamp = datetime.fromisoformat(trained_at).date()
    except ValueError:
        return None
    return (today - stamp).days


def decide_retrain(
    *,
    drift_status: str,
    age_days: int | None,
    max_model_age_days: int | None,
) -> RetrainDecision:
    """Decide whether a model warrants a retrain.

    Triggers when the latest PSI drift status is ``"alert"`` or when the active
    bundle is at/over the configured age cap. Any other status
    (``"ok"``/``"warning"``/``"low_sample"``/``"unknown"``) does not trigger on
    drift alone — a warning is informational, not yet actionable.
    """
    reasons: list[str] = []
    if drift_status == "alert":
        reasons.append("feature drift PSI in alert band")
    if (
        max_model_age_days is not None
        and age_days is not None
        and age_days >= max_model_age_days
    ):
        reasons.append(f"model age {age_days}d >= {max_model_age_days}d cap")
    return RetrainDecision(should_retrain=bool(reasons), reasons=reasons)
