"""ML projection endpoint (context doc §9.7, §12.1)."""

from __future__ import annotations

import math

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from kospi_flow.api.deps import get_session
from kospi_flow.api.envelope import envelope, make_metadata, not_found
from kospi_flow.core.models import DimStock, FactMlPredictionDaily, FactPriceDaily

router = APIRouter(prefix="/stocks", tags=["projection"])


@router.get("/{ticker}/projection")
def projection(ticker: str, session: Session = Depends(get_session)) -> dict:
    """Latest stored predictions for a ticker, one entry per horizon."""
    if session.get(DimStock, ticker) is None:
        raise not_found(f"Unknown ticker '{ticker}'.", ticker=ticker)

    latest_date = session.scalar(
        select(FactMlPredictionDaily.date)
        .where(FactMlPredictionDaily.ticker == ticker)
        .order_by(FactMlPredictionDaily.date.desc())
        .limit(1)
    )
    if latest_date is None:
        raise not_found(
            "No ML projection available for this ticker. Run training + inference.",
            ticker=ticker,
        )

    rows = session.execute(
        select(FactMlPredictionDaily)
        .where(FactMlPredictionDaily.ticker == ticker)
        .where(FactMlPredictionDaily.date == latest_date)
        .order_by(FactMlPredictionDaily.horizon_days)
    ).scalars().all()

    close = session.scalar(
        select(FactPriceDaily.close)
        .where(FactPriceDaily.ticker == ticker)
        .order_by(FactPriceDaily.date.desc())
        .limit(1)
    )

    def _price(close_v, log_ret):
        if close_v is None or log_ret is None:
            return None
        return close_v * math.exp(log_ret)

    data = []
    for r in rows:
        data.append(
            {
                "horizon_days": r.horizon_days,
                "expected_return": r.predicted_return,
                "projected_price": r.predicted_price,
                "prediction_band": {
                    "bear_price": _price(close, r.predicted_return_p10),
                    "base_price": _price(close, r.predicted_return_p50),
                    "bull_price": _price(close, r.predicted_return_p90),
                    "p10_return": r.predicted_return_p10,
                    "p50_return": r.predicted_return_p50,
                    "p90_return": r.predicted_return_p90,
                },
                "prob_outperform_kospi": r.prob_outperform_kospi,
                "model_name": r.model_name,
                "model_version": r.model_version,
                "feature_version": r.feature_version,
            }
        )
    meta = make_metadata(latest_data_date=latest_date)
    # Uncertainty disclaimer — never present as a guaranteed price (§19.3).
    meta["disclaimer"] = (
        "예측치는 불확실성을 포함하며 확정 가격이 아닙니다 "
        "(projection includes uncertainty; not a guaranteed price)."
    )
    return envelope({"latest_date": latest_date.isoformat(), "projections": data}, meta)
