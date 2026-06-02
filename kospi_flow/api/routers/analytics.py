"""Correlation and event-study endpoints (context doc §12.1, Phase 3)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from kospi_flow.analytics.events import EVENT_TYPES
from kospi_flow.analytics.service import stock_correlations, stock_event_study
from kospi_flow.api.deps import get_session
from kospi_flow.api.envelope import envelope, make_metadata, not_found
from kospi_flow.core.enums import MVP_INVESTOR_GROUPS
from kospi_flow.core.models import DimStock

router = APIRouter(prefix="/stocks", tags=["analytics"])


def _require_stock(session: Session, ticker: str) -> None:
    if session.get(DimStock, ticker) is None:
        raise not_found(f"Unknown ticker '{ticker}'.", ticker=ticker)


@router.get("/{ticker}/correlations")
def correlations(
    ticker: str,
    session: Session = Depends(get_session),
    investor_groups: str = Query(
        default=",".join(g.value for g in MVP_INVESTOR_GROUPS),
        description="Comma-separated investor groups",
    ),
) -> dict:
    _require_stock(session, ticker)
    groups = [g.strip() for g in investor_groups.split(",") if g.strip()]
    results = stock_correlations(session, ticker, groups)
    if not results:
        raise not_found("Not enough data to compute correlations.", ticker=ticker)
    return envelope(
        [r.as_dict() for r in results],
        make_metadata(note="Pearson/Spearman of trailing net-buy %mcap vs forward return"),
    )


@router.get("/{ticker}/events")
def events(
    ticker: str,
    session: Session = Depends(get_session),
    event_type: str = Query(default="foreign_accumulation"),
) -> dict:
    _require_stock(session, ticker)
    if event_type not in EVENT_TYPES:
        raise not_found(
            f"Unknown event_type '{event_type}'.",
            valid_event_types=list(EVENT_TYPES),
        )
    result = stock_event_study(session, ticker, event_type)
    return envelope(result, make_metadata(event_type=event_type))


@router.get("/{ticker}/flow-return-profile")
def flow_return_profile(
    ticker: str,
    session: Session = Depends(get_session),
    flow_window: int = Query(default=5, ge=1, le=120),
) -> dict:
    """Quintile breakdown of subsequent return vs trailing net-buy strength."""
    _require_stock(session, ticker)
    from kospi_flow.analytics.service import stock_flow_return_profile

    data = stock_flow_return_profile(session, ticker, flow_window=flow_window)
    return envelope(
        data,
        make_metadata(
            note="Mean forward return by quintile of trailing net-buy %mcap "
            "(Q1=net-sell … Q5=net-buy); no look-ahead."
        ),
    )
