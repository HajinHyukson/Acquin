"""ML projection + historical prediction-accuracy endpoints (context doc §9.7).

Multiple models coexist in ``fact_ml_prediction_daily`` (PK includes
``model_name``): the internal per-horizon ``gbm_return_<h>d`` bundles, external
models pushed via ``POST /models/{name}/predictions``, and ``wf::``-prefixed
walk-forward backtest rows. Projections group internal names into one
``gbm_return`` family (one row per horizon) and each external model into its
own family; backtest rows are excluded everywhere except the accuracy endpoint.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from kospi_flow.api.deps import get_session
from kospi_flow.api.envelope import envelope, make_metadata, not_found
from kospi_flow.core.models import DimStock, FactMlPredictionDaily, FactPriceDaily
from kospi_flow.ml.backtest import BACKTEST_PREFIX, backtest_model_name

router = APIRouter(prefix="/stocks", tags=["projection"])

#: Internal per-horizon models share one family so the projection table shows
#: one row per horizon (as before) rather than one group per horizon model.
INTERNAL_FAMILY = "gbm_return"


def model_family(name: str) -> str:
    return INTERNAL_FAMILY if name.startswith("gbm_return_") else name


def _price(close_v, log_ret):
    if close_v is None or log_ret is None:
        return None
    return close_v * math.exp(log_ret)


def _projection_entry(r: FactMlPredictionDaily, close) -> dict:
    return {
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


@router.get("/{ticker}/projection")
def projection(
    ticker: str,
    model: str | None = Query(
        default=None,
        description=f"Model family to feature ('{INTERNAL_FAMILY}' or an "
        "external model name). Default: internal if present, else first.",
    ),
    session: Session = Depends(get_session),
) -> dict:
    """Latest stored predictions for a ticker, grouped per model family.

    Response keeps the original shape (``latest_date`` + ``projections`` from
    the featured family) and adds ``models`` with every family's projections so
    the frontend can render external models alongside the internal one.
    """
    if session.get(DimStock, ticker) is None:
        raise not_found(f"Unknown ticker '{ticker}'.", ticker=ticker)

    rows = session.execute(
        select(FactMlPredictionDaily)
        .where(FactMlPredictionDaily.ticker == ticker)
        .where(FactMlPredictionDaily.model_name.notlike(f"{BACKTEST_PREFIX}%"))
        .order_by(FactMlPredictionDaily.horizon_days)
    ).scalars().all()
    if not rows:
        raise not_found(
            "No ML projection available for this ticker. Run training + inference.",
            ticker=ticker,
        )

    close = session.scalar(
        select(FactPriceDaily.close)
        .where(FactPriceDaily.ticker == ticker)
        .order_by(FactPriceDaily.date.desc())
        .limit(1)
    )

    by_family: dict[str, list[FactMlPredictionDaily]] = {}
    for r in rows:
        by_family.setdefault(model_family(r.model_name), []).append(r)

    groups = []
    for family, members in by_family.items():
        latest = max(r.date for r in members)
        latest_rows = sorted(
            (r for r in members if r.date == latest), key=lambda r: r.horizon_days
        )
        groups.append(
            {
                "model": family,
                "source": "internal" if family == INTERNAL_FAMILY else "external",
                "latest_date": latest.isoformat(),
                "projections": [_projection_entry(r, close) for r in latest_rows],
            }
        )
    groups.sort(key=lambda g: (g["source"] != "internal", g["model"]))

    featured = next((g for g in groups if g["model"] == model), None) if model else None
    if model and featured is None:
        raise not_found(
            f"No projections from model '{model}' for this ticker.",
            ticker=ticker,
            available_models=[g["model"] for g in groups],
        )
    featured = featured or groups[0]

    meta = make_metadata(latest_data_date=None)
    meta["latest_data_date"] = featured["latest_date"]
    # Uncertainty disclaimer — never present as a guaranteed price (§19.3).
    meta["disclaimer"] = (
        "예측치는 불확실성을 포함하며 확정 가격이 아닙니다 "
        "(projection includes uncertainty; not a guaranteed price)."
    )
    return envelope(
        {
            "latest_date": featured["latest_date"],
            "projections": featured["projections"],
            "model": featured["model"],
            "models": groups,
        },
        meta,
    )


@router.get("/{ticker}/prediction-accuracy")
def prediction_accuracy(
    ticker: str,
    horizon: int = Query(default=5, ge=1, le=60),
    model: str | None = Query(
        default=None,
        description="Base model name (default: internal gbm_return_<h>d). Both "
        "its live rows and its wf:: backtest rows are evaluated.",
    ),
    rolling_window: int = Query(default=60, ge=5, le=252),
    session: Session = Depends(get_session),
) -> dict:
    """Historical prediction record vs what actually happened (§9.7 extension).

    Joins stored predictions (walk-forward backtest rows + matured live rows)
    with realized forward returns from prices. Powers the stock-page accuracy
    panel: band-vs-actual ribbon, scorecard, and rolling hit rate. Leak-free by
    construction — every row was predicted using only data up to its date.
    """
    if session.get(DimStock, ticker) is None:
        raise not_found(f"Unknown ticker '{ticker}'.", ticker=ticker)

    base_name = model or f"gbm_return_{horizon}d"
    names = [base_name, backtest_model_name(base_name)]
    preds = session.execute(
        select(FactMlPredictionDaily)
        .where(FactMlPredictionDaily.ticker == ticker)
        .where(FactMlPredictionDaily.horizon_days == horizon)
        .where(FactMlPredictionDaily.model_name.in_(names))
        .order_by(FactMlPredictionDaily.date)
    ).scalars().all()
    if not preds:
        raise not_found(
            "No historical predictions for this ticker/horizon yet. Run the "
            "walk-forward backtest (`python -m kospi_flow.cli backtest`).",
            ticker=ticker,
            horizon=horizon,
            model=base_name,
        )

    # Live row wins over the backtest row on the same date (it is the genuine
    # production prediction; the wf row is its simulation).
    by_date: dict = {}
    for p in preds:  # wf:: first, live second -> live overwrites
        if p.model_name.startswith(BACKTEST_PREFIX):
            by_date[p.date] = p
    for p in preds:
        if not p.model_name.startswith(BACKTEST_PREFIX):
            by_date[p.date] = p

    price_rows = session.execute(
        select(FactPriceDaily.date, FactPriceDaily.close, FactPriceDaily.adj_close)
        .where(FactPriceDaily.ticker == ticker)
        .order_by(FactPriceDaily.date)
    ).all()
    dates = [r[0] for r in price_rows]
    closes = [r[1] for r in price_rows]
    adjs = [r[2] if r[2] is not None else r[1] for r in price_rows]
    pos = {d: i for i, d in enumerate(dates)}

    rows: list[dict] = []
    for d in sorted(by_date):
        p = by_date[d]
        i = pos.get(d)
        if i is None or p.predicted_return is None:
            continue
        j = i + horizon
        if j >= len(dates) or not adjs[i] or not adjs[j]:
            continue  # outcome not yet known (or price gap)
        realized = math.log(adjs[j] / adjs[i])
        hit = (p.predicted_return >= 0) == (realized >= 0)
        within = (
            p.predicted_return_p10 is not None
            and p.predicted_return_p90 is not None
            and p.predicted_return_p10 <= realized <= p.predicted_return_p90
        )
        rows.append(
            {
                "date": d.isoformat(),
                "target_date": dates[j].isoformat(),
                "predicted_return": p.predicted_return,
                "realized_return": realized,
                "p10_return": p.predicted_return_p10,
                "p50_return": p.predicted_return_p50,
                "p90_return": p.predicted_return_p90,
                # Band translated to prices at the target date for the ribbon.
                "p10_price": _price(closes[i], p.predicted_return_p10),
                "p50_price": _price(closes[i], p.predicted_return_p50),
                "p90_price": _price(closes[i], p.predicted_return_p90),
                "actual_price": closes[j],
                "direction_hit": hit,
                "within_band": within,
                "is_live": not p.model_name.startswith(BACKTEST_PREFIX),
            }
        )

    if not rows:
        raise not_found(
            "Predictions exist but none have matured outcomes yet.",
            ticker=ticker,
            horizon=horizon,
        )

    pred_s = pd.Series([r["predicted_return"] for r in rows])
    real_s = pd.Series([r["realized_return"] for r in rows])
    err = (pred_s - real_s).abs()
    hits = pd.Series([r["direction_hit"] for r in rows], dtype=float)
    summary = {
        "n": len(rows),
        "direction_hit_rate": float(hits.mean()),
        "band_coverage": float(np.mean([r["within_band"] for r in rows])),
        "mae": float(err.mean()),
        "rmse": float(np.sqrt(((pred_s - real_s) ** 2).mean())),
        "spearman_ic": (
            float(pred_s.corr(real_s, method="spearman")) if len(rows) >= 10 else None
        ),
        "first_date": rows[0]["date"],
        "last_date": rows[-1]["date"],
        "n_live": int(sum(r["is_live"] for r in rows)),
    }
    rolling = hits.rolling(rolling_window, min_periods=max(5, rolling_window // 3)).mean()
    rolling_hit_rate = [
        {"date": rows[i]["date"], "hit_rate": float(v)}
        for i, v in enumerate(rolling)
        if not np.isnan(v)
    ]

    meta = make_metadata(latest_data_date=None)
    meta["latest_data_date"] = rows[-1]["date"]
    meta["disclaimer"] = (
        "과거 시점 데이터만으로 학습한 모델의 워크포워드 기록이며, "
        "미래 성과를 보장하지 않습니다 (walk-forward record; not a guarantee)."
    )
    return envelope(
        {
            "ticker": ticker,
            "horizon_days": horizon,
            "model_name": base_name,
            "summary": summary,
            "rolling_window": rolling_window,
            "rolling_hit_rate": rolling_hit_rate,
            "rows": rows,
        },
        meta,
    )
