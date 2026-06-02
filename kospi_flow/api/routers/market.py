"""Market-level endpoints."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from kospi_flow.analytics.market import (
    benchmark_return_series,
    benchmark_source,
    index_level_series,
    load_price_panel,
)
from kospi_flow.api.deps import get_session
from kospi_flow.api.envelope import envelope, make_metadata
from kospi_flow.core.enums import MVP_INVESTOR_GROUPS
from kospi_flow.core.models import (
    DimStock,
    FactInvestorFlowDaily,
    FactMlPredictionDaily,
    FactPriceDaily,
)

router = APIRouter(prefix="/market", tags=["market"])


def _trailing_dates(session: Session, n: int) -> list[date]:
    return [
        d for (d,) in session.execute(
            select(FactPriceDaily.date)
            .distinct()
            .order_by(FactPriceDaily.date.desc())
            .limit(n)
        ).all()
    ]


@router.get("/overview")
def market_overview(session: Session = Depends(get_session)) -> dict:
    """Benchmark daily return (real KOSPI index if ingested, else proxy)."""
    panel = load_price_panel(session)
    n_stocks = session.scalar(select(func.count()).select_from(DimStock)) or 0
    if panel.empty:
        return envelope({"n_stocks": n_stocks, "market_return_1d": None})

    daily = benchmark_return_series(session)
    source = benchmark_source(session)
    index_level = index_level_series(session)
    latest_date = panel["date"].max()
    latest = panel[panel["date"] == latest_date]
    data = {
        "n_stocks": n_stocks,
        "as_of": latest_date.isoformat(),
        "market_return_1d": float(daily.iloc[-1]) if len(daily) else None,
        "benchmark_source": source,
        "index_level": float(index_level.iloc[-1]) if len(index_level) else None,
        "total_market_cap": float(latest["market_cap"].sum(skipna=True)),
        "total_trading_value": float(latest["trading_value"].sum(skipna=True)),
    }
    return envelope(
        data, make_metadata(latest_data_date=latest_date, benchmark_source=source)
    )


@router.get("/top-net-buy")
def top_net_buy(
    session: Session = Depends(get_session),
    investor_group: str = "foreign",
    lookback_days: int = Query(default=5, ge=1, le=252),
    limit: int = Query(default=20, ge=1, le=200),
) -> dict:
    """Naver-style ranking by recent net-buy amount for one investor group."""
    # Determine the trailing window of dates from the global price calendar.
    dates = [
        d for (d,) in session.execute(
            select(FactPriceDaily.date).distinct().order_by(FactPriceDaily.date.desc())
            .limit(lookback_days)
        ).all()
    ]
    if not dates:
        return envelope([], make_metadata())

    rows = session.execute(
        select(
            FactInvestorFlowDaily.ticker,
            func.sum(FactInvestorFlowDaily.net_buy_amount),
            func.sum(FactInvestorFlowDaily.net_buy_volume),
        )
        .where(FactInvestorFlowDaily.investor_group == investor_group)
        .where(FactInvestorFlowDaily.date.in_(dates))
        .group_by(FactInvestorFlowDaily.ticker)
    ).all()
    names = dict(session.execute(select(DimStock.ticker, DimStock.name_kr)).all())
    ranked = sorted(rows, key=lambda r: (r[1] or 0.0), reverse=True)[:limit]
    data = [
        {
            "rank": i + 1,
            "ticker": t,
            "name_kr": names.get(t),
            "net_buy_amount": float(amt or 0.0),
            "net_buy_volume": float(vol or 0.0),
        }
        for i, (t, amt, vol) in enumerate(ranked)
    ]
    return envelope(
        data,
        make_metadata(
            latest_data_date=max(dates),
            investor_group=investor_group,
            lookback_days=lookback_days,
        ),
    )


@router.get("/investor-flows")
def market_investor_flows(
    session: Session = Depends(get_session),
    lookback_days: int = Query(default=20, ge=1, le=252),
) -> dict:
    """Aggregate daily net buy by investor group across the whole market."""
    dates = [
        d for (d,) in session.execute(
            select(FactPriceDaily.date).distinct().order_by(FactPriceDaily.date.desc())
            .limit(lookback_days)
        ).all()
    ]
    if not dates:
        return envelope({})
    rows = session.execute(
        select(
            FactInvestorFlowDaily.date,
            FactInvestorFlowDaily.investor_group,
            func.sum(FactInvestorFlowDaily.net_buy_amount),
        )
        .where(FactInvestorFlowDaily.date.in_(dates))
        .where(
            FactInvestorFlowDaily.investor_group.in_(
                [g.value for g in MVP_INVESTOR_GROUPS]
            )
        )
        .group_by(FactInvestorFlowDaily.date, FactInvestorFlowDaily.investor_group)
        .order_by(FactInvestorFlowDaily.date)
    ).all()
    by_group: dict[str, list[dict]] = {}
    for d, g, amt in rows:
        by_group.setdefault(g, []).append(
            {"date": d.isoformat(), "net_buy_amount": float(amt or 0.0)}
        )
    return envelope({"by_group": by_group}, make_metadata(latest_data_date=max(dates)))


@router.get("/index")
def market_index(
    session: Session = Depends(get_session),
    index_code: str | None = None,
    start: str | None = None,
    end: str | None = None,
) -> dict:
    """Benchmark index OHLC series (real index if ingested, else proxy level)."""
    from kospi_flow.analytics.market import (
        benchmark_index_level,
        benchmark_source,
        load_index_series,
    )

    real = load_index_series(session, index_code)
    if not real.empty:
        df = real
        if start:
            df = df[df["date"] >= date.fromisoformat(start)]
        if end:
            df = df[df["date"] <= date.fromisoformat(end)]
        data = [
            {
                "date": r.date.isoformat(),
                "close": r.close,
                "return_1d": None if r.return_1d != r.return_1d else r.return_1d,
            }
            for r in df.itertuples(index=False)
        ]
    else:
        # Proxy level (base=1000) when no real index has been ingested.
        level = benchmark_index_level(session)
        data = [
            {"date": d.isoformat(), "close": float(v), "return_1d": None}
            for d, v in level.items()
        ]
    meta = make_metadata(benchmark_source=benchmark_source(session, index_code))
    return envelope(data, meta)


@router.get("/top-picks")
def top_picks(
    session: Session = Depends(get_session),
    horizon: int = Query(default=5, ge=1, le=60),
    limit: int = Query(default=20, ge=1, le=100),
    lookback_days: int = Query(default=5, ge=1, le=60),
    notable_only: bool = True,
) -> dict:
    """Today's top ML picks: highest predicted return, among stocks with recent
    notable buying (외국인+기관 net buy > 0 over the lookback window).

    Ranked by the latest stored prediction for ``horizon``. Set
    ``notable_only=false`` to rank purely by ML projection.
    """
    latest_date = session.scalar(
        select(func.max(FactMlPredictionDaily.date)).where(
            FactMlPredictionDaily.horizon_days == horizon
        )
    )
    if latest_date is None:
        return envelope(
            [], make_metadata(note="No ML predictions yet (run train + predict).")
        )

    preds = session.execute(
        select(
            FactMlPredictionDaily.ticker,
            FactMlPredictionDaily.predicted_return,
            FactMlPredictionDaily.predicted_price,
            FactMlPredictionDaily.prob_outperform_kospi,
        )
        .where(FactMlPredictionDaily.horizon_days == horizon)
        .where(FactMlPredictionDaily.date == latest_date)
    ).all()
    best: dict[str, tuple] = {}
    for tk, pr, pp, prob in preds:
        if pr is None:
            continue
        if tk not in best or pr > best[tk][0]:
            best[tk] = (pr, pp, prob)
    if not best:
        return envelope([], make_metadata(latest_data_date=latest_date))

    dates = _trailing_dates(session, lookback_days)
    flows: dict[str, dict[str, float]] = {}
    if dates:
        rows = session.execute(
            select(
                FactInvestorFlowDaily.ticker,
                FactInvestorFlowDaily.investor_group,
                func.sum(FactInvestorFlowDaily.net_buy_amount),
            )
            .where(FactInvestorFlowDaily.date.in_(dates))
            .where(
                FactInvestorFlowDaily.investor_group.in_(
                    [g.value for g in MVP_INVESTOR_GROUPS]
                )
            )
            .group_by(FactInvestorFlowDaily.ticker, FactInvestorFlowDaily.investor_group)
        ).all()
        for tk, grp, amt in rows:
            flows.setdefault(tk, {})[grp] = float(amt or 0.0)

    names = dict(session.execute(select(DimStock.ticker, DimStock.name_kr)).all())

    cands = []
    for tk, (pr, pp, prob) in best.items():
        f = flows.get(tk, {})
        foreign = f.get("foreign", 0.0)
        inst = f.get("institution", 0.0)
        retail = f.get("retail", 0.0)
        if notable_only and (foreign + inst) <= 0:
            continue
        cands.append(
            {
                "ticker": tk,
                "name_kr": names.get(tk),
                "predicted_return": pr,
                "predicted_price": pp,
                "prob_outperform_kospi": prob,
                "foreign_net": foreign,
                "institution_net": inst,
                "retail_net": retail,
            }
        )
    cands.sort(key=lambda c: c["predicted_return"], reverse=True)
    data = [{**c, "rank": i} for i, c in enumerate(cands[:limit], start=1)]
    return envelope(
        data,
        make_metadata(
            latest_data_date=latest_date,
            horizon_days=horizon,
            lookback_days=lookback_days,
            notable_only=notable_only,
        ),
    )


@router.get("/closes")
def closes(
    session: Session = Depends(get_session),
    tickers: str = "",
    days: int = Query(default=20, ge=2, le=250),
) -> dict:
    """Recent close prices for many tickers in one call (for sparklines).

    Returns ``{ticker: [close, ...]}`` ascending by date.
    """
    tks = [t.strip() for t in tickers.split(",") if t.strip()][:100]
    if not tks:
        return envelope({})
    dates = _trailing_dates(session, days)
    if not dates:
        return envelope({})
    rows = session.execute(
        select(FactPriceDaily.ticker, FactPriceDaily.date, FactPriceDaily.close)
        .where(FactPriceDaily.ticker.in_(tks))
        .where(FactPriceDaily.date.in_(dates))
        .order_by(FactPriceDaily.ticker, FactPriceDaily.date)
    ).all()
    out: dict[str, list[float | None]] = {}
    for tk, _d, c in rows:
        out.setdefault(tk, []).append(c)
    return envelope(out, make_metadata(latest_data_date=max(dates)))
