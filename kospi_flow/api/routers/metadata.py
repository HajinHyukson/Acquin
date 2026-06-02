"""Health and data-freshness endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from kospi_flow.api.deps import get_session
from kospi_flow.api.envelope import envelope, make_metadata
from kospi_flow.core.models import (
    FactForeignHoldingDaily,
    FactInvestorFlowDaily,
    FactPriceDaily,
)

router = APIRouter(tags=["metadata"])

_TABLES = {
    "fact_price_daily": FactPriceDaily,
    "fact_investor_flow_daily": FactInvestorFlowDaily,
    "fact_foreign_holding_daily": FactForeignHoldingDaily,
}


@router.get("/health")
def health() -> dict:
    return envelope({"status": "ok"})


@router.get("/metadata/data-freshness")
def data_freshness(session: Session = Depends(get_session)) -> dict:
    """Latest data date and freshness state per fact table."""
    out: dict[str, dict] = {}
    for name, model in _TABLES.items():
        max_date = session.scalar(select(func.max(model.date)))
        latest_state = None
        source = None
        if max_date is not None:
            row = session.execute(
                select(model.freshness_state, model.source)
                .where(model.date == max_date)
                .limit(1)
            ).first()
            if row:
                latest_state, source = row
        out[name] = {
            "latest_data_date": max_date.isoformat() if max_date else None,
            "freshness_state": latest_state,
            "source": source,
            "row_count": session.scalar(select(func.count()).select_from(model)),
        }
    return envelope(out, make_metadata())
