"""Stock list and stock-detail endpoints."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from kospi_flow.api.deps import get_session
from kospi_flow.api.envelope import envelope, make_metadata, not_found
from kospi_flow.core.models import (
    DimStock,
    FactFeaturesDaily,
    FactForeignHoldingDaily,
    FactInvestorFlowDaily,
    FactPriceDaily,
)

router = APIRouter(prefix="/stocks", tags=["stocks"])


def _require_stock(session: Session, ticker: str) -> DimStock:
    stock = session.get(DimStock, ticker)
    if stock is None:
        raise not_found(f"Unknown ticker '{ticker}'.", ticker=ticker)
    return stock


def _fact_metadata(session: Session, model, ticker: str) -> dict:
    """Metadata (latest date + freshness) for a ticker in a fact table."""
    row = session.execute(
        select(model.date, model.freshness_state, model.source)
        .where(model.ticker == ticker)
        .order_by(model.date.desc())
        .limit(1)
    ).first()
    if not row:
        return make_metadata()
    return make_metadata(
        source=row[2], freshness_state=row[1], latest_data_date=row[0]
    )


@router.get("")
def list_stocks(
    session: Session = Depends(get_session),
    market: str = "KOSPI",
    active_only: bool = True,
    limit: int = Query(default=500, ge=1, le=5000),
) -> dict:
    stmt = select(DimStock).where(DimStock.market == market)
    if active_only:
        stmt = stmt.where(DimStock.is_active.is_(True))
    stmt = stmt.order_by(DimStock.ticker).limit(limit)
    stocks = session.execute(stmt).scalars().all()
    data = [
        {
            "ticker": s.ticker,
            "name_kr": s.name_kr,
            "name_en": s.name_en,
            "sector": s.sector,
            "market": s.market,
            "is_preferred": s.is_preferred,
            "is_active": s.is_active,
        }
        for s in stocks
    ]
    return envelope(data, make_metadata(extra_count=len(data)))


@router.get("/{ticker}")
def stock_detail(ticker: str, session: Session = Depends(get_session)) -> dict:
    """Overview section: identity + latest price snapshot + recent returns."""
    stock = _require_stock(session, ticker)
    latest = session.execute(
        select(FactPriceDaily)
        .where(FactPriceDaily.ticker == ticker)
        .order_by(FactPriceDaily.date.desc())
        .limit(1)
    ).scalar_one_or_none()

    overview = {
        "ticker": stock.ticker,
        "name_kr": stock.name_kr,
        "name_en": stock.name_en,
        "sector": stock.sector,
        "market": stock.market,
        "is_preferred": stock.is_preferred,
    }
    if latest is not None:
        prices = session.execute(
            select(FactPriceDaily.date, FactPriceDaily.close)
            .where(FactPriceDaily.ticker == ticker)
            .order_by(FactPriceDaily.date.desc())
            .limit(21)
        ).all()
        closes = [c for (_d, c) in prices if c is not None]

        def _ret(n: int) -> float | None:
            if len(closes) > n and closes[n]:
                return closes[0] / closes[n] - 1.0
            return None

        overview.update(
            {
                "as_of": latest.date.isoformat(),
                "close": latest.close,
                "market_cap": latest.market_cap,
                "return_1d": _ret(1),
                "return_5d": _ret(5),
                "return_20d": _ret(20),
                "freshness_state": latest.freshness_state,
            }
        )
        meta = make_metadata(
            source=latest.source,
            freshness_state=latest.freshness_state,
            latest_data_date=latest.date,
        )
    else:
        meta = make_metadata()
    return envelope(overview, meta)


def _date_filter(stmt, model, start: date | None, end: date | None):
    if start:
        stmt = stmt.where(model.date >= start)
    if end:
        stmt = stmt.where(model.date <= end)
    return stmt


@router.get("/{ticker}/price")
def stock_price(
    ticker: str,
    session: Session = Depends(get_session),
    start: date | None = None,
    end: date | None = None,
) -> dict:
    _require_stock(session, ticker)
    stmt = _date_filter(
        select(FactPriceDaily).where(FactPriceDaily.ticker == ticker),
        FactPriceDaily,
        start,
        end,
    ).order_by(FactPriceDaily.date)
    rows = session.execute(stmt).scalars().all()
    if not rows:
        raise not_found("No price data for this ticker/range.", ticker=ticker)
    data = [
        {
            "date": r.date.isoformat(),
            "open": r.open,
            "high": r.high,
            "low": r.low,
            "close": r.close,
            "adj_close": r.adj_close,
            "volume": r.volume,
            "trading_value": r.trading_value,
            "market_cap": r.market_cap,
            "return_1d": r.return_1d,
        }
        for r in rows
    ]
    return envelope(data, _fact_metadata(session, FactPriceDaily, ticker))


@router.get("/{ticker}/investor-flows")
def stock_investor_flows(
    ticker: str,
    session: Session = Depends(get_session),
    start: date | None = None,
    end: date | None = None,
    cumulative: bool = False,
) -> dict:
    """Daily 개인/기관/외국인 순매수, optionally cumulative (포지션 프록시)."""
    _require_stock(session, ticker)
    stmt = _date_filter(
        select(FactInvestorFlowDaily).where(FactInvestorFlowDaily.ticker == ticker),
        FactInvestorFlowDaily,
        start,
        end,
    ).order_by(FactInvestorFlowDaily.date)
    rows = session.execute(stmt).scalars().all()
    if not rows:
        raise not_found("No investor-flow data for this ticker/range.", ticker=ticker)

    by_group: dict[str, list[dict]] = {}
    for r in rows:
        by_group.setdefault(r.investor_group, []).append(
            {
                "date": r.date.isoformat(),
                "net_buy_amount": r.net_buy_amount,
                "net_buy_volume": r.net_buy_volume,
            }
        )
    if cumulative:
        for series in by_group.values():
            cum_amt = 0.0
            cum_vol = 0.0
            for pt in series:
                cum_amt += pt["net_buy_amount"] or 0.0
                cum_vol += pt["net_buy_volume"] or 0.0
                pt["cumulative_net_buy_amount"] = cum_amt
                pt["cumulative_net_buy_volume"] = cum_vol

    meta = _fact_metadata(session, FactInvestorFlowDaily, ticker)
    # Make the proxy nature explicit for retail/institution cumulative series.
    meta["note"] = (
        "누적 순매수는 실제 보유량이 아닌 기준일 이후 순매수 누적값입니다 "
        "(cumulative net-buy proxy, not actual holdings)."
    )
    return envelope({"by_group": by_group}, meta)


@router.get("/{ticker}/foreign-holdings")
def stock_foreign_holdings(
    ticker: str,
    session: Session = Depends(get_session),
    start: date | None = None,
    end: date | None = None,
) -> dict:
    """외국인 보유량 / 보유비율 — the only true-holding series."""
    _require_stock(session, ticker)
    stmt = _date_filter(
        select(FactForeignHoldingDaily).where(
            FactForeignHoldingDaily.ticker == ticker
        ),
        FactForeignHoldingDaily,
        start,
        end,
    ).order_by(FactForeignHoldingDaily.date)
    rows = session.execute(stmt).scalars().all()
    if not rows:
        raise not_found("No foreign-holding data for this ticker.", ticker=ticker)
    data = [
        {
            "date": r.date.isoformat(),
            "foreign_held_shares": r.foreign_held_shares,
            "foreign_ownership_pct": r.foreign_ownership_pct,
            "foreign_limit_exhaustion_pct": r.foreign_limit_exhaustion_pct,
        }
        for r in rows
    ]
    return envelope(data, _fact_metadata(session, FactForeignHoldingDaily, ticker))


@router.get("/{ticker}/features")
def stock_features(
    ticker: str,
    session: Session = Depends(get_session),
    start: date | None = None,
    end: date | None = None,
) -> dict:
    _require_stock(session, ticker)
    stmt = _date_filter(
        select(FactFeaturesDaily).where(FactFeaturesDaily.ticker == ticker),
        FactFeaturesDaily,
        start,
        end,
    ).order_by(FactFeaturesDaily.date)
    rows = session.execute(stmt).scalars().all()
    if not rows:
        raise not_found("No feature data for this ticker.", ticker=ticker)
    data = [
        {
            "date": r.date.isoformat(),
            "feature_version": r.feature_version,
            "foreign_net_5d_amt": r.foreign_net_5d_amt,
            "institution_net_20d_pct_mcap": r.institution_net_20d_pct_mcap,
            "retail_streak_days": r.retail_streak_days,
            "foreign_flow_z_60d": r.foreign_flow_z_60d,
            "price_return_5d": r.price_return_5d,
            "volatility_20d": r.volatility_20d,
        }
        for r in rows
    ]
    return envelope(data, make_metadata(latest_data_date=rows[-1].date))


# Phase 3 / Phase 4 endpoints (correlations, events, projection) are registered
# from their own routers in those phases.
