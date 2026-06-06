"""Alert rule engine (Phase 5).

Evaluates conditions over the database and returns a list of :class:`Alert`.
Rules are intentionally simple and pure (given a session) so they are testable.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from kospi_flow.alerts.notifier import Alert
from kospi_flow.core.config import Settings, get_settings
from kospi_flow.core.db import Database
from kospi_flow.core.enums import InvestorGroup
from kospi_flow.core.models import (
    FactInvestorFlowDaily,
    FactModelDriftDaily,
    FactPriceDaily,
    WatchlistItem,
)

#: Default watchlist trigger: |foreign 5D net buy| >= ₩50B.
DEFAULT_WATCHLIST_FLOW_THRESHOLD = 50_000_000_000.0


def _validation_alerts(report) -> list[Alert]:
    alerts: list[Alert] = []
    if report is not None and not report.ok:
        alerts.append(
            Alert(
                code="DATA_VALIDATION_FAILED",
                severity="critical",
                message=f"{len(report.errors)} data-validation error(s) detected",
                context={"errors": [i.message for i in report.errors][:10]},
            )
        )
    return alerts


def _drift_alerts(session: Session) -> list[Alert]:
    """Alert on the latest drift status per model."""
    alerts: list[Alert] = []
    latest_date = session.scalar(select(func.max(FactModelDriftDaily.date)))
    if latest_date is None:
        return alerts
    rows = session.execute(
        select(FactModelDriftDaily).where(FactModelDriftDaily.date == latest_date)
    ).scalars().all()
    for r in rows:
        if r.status == "alert":
            alerts.append(
                Alert(
                    code="MODEL_DRIFT_ALERT",
                    severity="critical",
                    message=f"Model '{r.model_name}' drift alert (max PSI={r.max_psi:.3f})",
                    context={"model_name": r.model_name, "max_psi": r.max_psi},
                )
            )
        elif r.status == "warning":
            alerts.append(
                Alert(
                    code="MODEL_DRIFT_WARNING",
                    severity="warning",
                    message=f"Model '{r.model_name}' drift warning (max PSI={r.max_psi:.3f})",
                    context={"model_name": r.model_name, "max_psi": r.max_psi},
                )
            )
    return alerts


def _retrain_alerts(session: Session) -> list[Alert]:
    """Recommend a retrain when the latest drift status is ``alert``.

    Complements ``_drift_alerts`` (which reports the drift): this one is the
    *actionable* signal a human/CI acts on when ``retrain_on_drift`` is off
    (the prod default — bundles are baked into the image). See context doc §24.2.
    """
    latest_date = session.scalar(select(func.max(FactModelDriftDaily.date)))
    if latest_date is None:
        return []
    rows = session.execute(
        select(FactModelDriftDaily).where(FactModelDriftDaily.date == latest_date)
    ).scalars().all()
    return [
        Alert(
            code="RETRAIN_RECOMMENDED",
            severity="warning",
            message=(
                f"Retrain recommended for '{r.model_name}' "
                f"(drift alert, max PSI={r.max_psi:.3f})"
            ),
            context={"model_name": r.model_name, "max_psi": r.max_psi},
        )
        for r in rows
        if r.status == "alert"
    ]


def _watchlist_flow_alerts(
    session: Session, threshold: float
) -> list[Alert]:
    """Alert when a watchlisted ticker has a large recent foreign net flow."""
    tickers = [
        t for (t,) in session.execute(
            select(WatchlistItem.ticker).distinct()
        ).all()
    ]
    if not tickers:
        return []
    # Trailing 5 trading dates from the global price calendar.
    dates = [
        d for (d,) in session.execute(
            select(FactPriceDaily.date)
            .distinct()
            .order_by(FactPriceDaily.date.desc())
            .limit(5)
        ).all()
    ]
    if not dates:
        return []
    rows = session.execute(
        select(
            FactInvestorFlowDaily.ticker,
            func.sum(FactInvestorFlowDaily.net_buy_amount),
        )
        .where(FactInvestorFlowDaily.ticker.in_(tickers))
        .where(FactInvestorFlowDaily.investor_group == InvestorGroup.FOREIGN.value)
        .where(FactInvestorFlowDaily.date.in_(dates))
        .group_by(FactInvestorFlowDaily.ticker)
    ).all()
    alerts: list[Alert] = []
    for ticker, net in rows:
        net = float(net or 0.0)
        if abs(net) >= threshold:
            direction = "순매수" if net > 0 else "순매도"
            alerts.append(
                Alert(
                    code="WATCHLIST_FLOW",
                    severity="info",
                    message=f"{ticker}: 외국인 5일 {direction} {net/1e8:,.0f}억",
                    context={"ticker": ticker, "foreign_net_5d": net},
                )
            )
    return alerts


def evaluate_alerts(
    database: Database,
    validation_report=None,
    settings: Settings | None = None,
    watchlist_flow_threshold: float = DEFAULT_WATCHLIST_FLOW_THRESHOLD,
) -> list[Alert]:
    """Run all alert rules and return the triggered alerts."""
    settings = settings or get_settings()
    alerts = list(_validation_alerts(validation_report))
    with database.session() as s:
        alerts.extend(_drift_alerts(s))
        alerts.extend(_retrain_alerts(s))
        alerts.extend(_watchlist_flow_alerts(s, watchlist_flow_threshold))
    return alerts
