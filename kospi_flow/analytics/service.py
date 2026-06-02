"""Analytics service: load a stock's data and run correlation/event studies.

Bridges the pure analytics functions with the database for the API layer.
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from kospi_flow.analytics.correlation import CorrelationResult, correlation_grid
from kospi_flow.analytics.events import event_study
from kospi_flow.analytics.labels import HORIZONS, forward_simple_return
from kospi_flow.analytics.market import benchmark_index_level
from kospi_flow.analytics.profile import flow_return_profile
from kospi_flow.core.enums import MVP_INVESTOR_GROUPS
from kospi_flow.core.models import FactInvestorFlowDaily, FactPriceDaily


def load_stock_frames(
    session: Session, ticker: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (price_df, flow_df) for one ticker, sorted by date."""
    price_rows = session.execute(
        select(
            FactPriceDaily.date,
            FactPriceDaily.open,
            FactPriceDaily.close,
            FactPriceDaily.adj_close,
            FactPriceDaily.market_cap,
        ).where(FactPriceDaily.ticker == ticker)
    ).all()
    price_df = pd.DataFrame(
        price_rows, columns=["date", "open", "close", "adj_close", "market_cap"]
    ).sort_values("date").reset_index(drop=True)

    flow_rows = session.execute(
        select(
            FactInvestorFlowDaily.date,
            FactInvestorFlowDaily.investor_group,
            FactInvestorFlowDaily.net_buy_amount,
        ).where(FactInvestorFlowDaily.ticker == ticker)
    ).all()
    flow_df = pd.DataFrame(
        flow_rows, columns=["date", "investor_group", "net_buy_amount"]
    )
    return price_df, flow_df


def _market_forward_returns(
    session: Session, dates: pd.Series, horizons: tuple[int, ...]
) -> dict[int, pd.Series]:
    """Benchmark forward simple returns aligned to ``dates`` (by position)."""
    level = benchmark_index_level(session)
    if level.empty:
        return {}
    aligned = level.reindex(dates.to_numpy()).reset_index(drop=True)
    return {h: forward_simple_return(aligned, h) for h in horizons}


def stock_correlations(
    session: Session,
    ticker: str,
    investor_groups: list[str],
    flow_windows: tuple[int, ...] = (5, 20),
    horizons: tuple[int, ...] = HORIZONS,
) -> list[CorrelationResult]:
    price_df, flow_df = load_stock_frames(session, ticker)
    if price_df.empty:
        return []
    return correlation_grid(price_df, flow_df, investor_groups, flow_windows, horizons)


def stock_event_study(
    session: Session,
    ticker: str,
    event_type: str,
    horizons: tuple[int, ...] = HORIZONS,
) -> dict:
    price_df, flow_df = load_stock_frames(session, ticker)
    if price_df.empty:
        return {"results": [], "matching_dates": []}
    market_fwd = _market_forward_returns(session, price_df["date"], horizons)
    results, dates = event_study(
        price_df, flow_df, event_type, market_fwd=market_fwd, horizons=horizons
    )
    return {
        "results": [r.as_dict() for r in results],
        "matching_dates": dates,
        "n_events": len(dates),
    }


def stock_flow_return_profile(
    session: Session,
    ticker: str,
    flow_window: int = 5,
    horizons: tuple[int, ...] = HORIZONS,
) -> dict:
    """Quintile profile of forward return vs trailing net-buy %mcap for a stock."""
    price_df, flow_df = load_stock_frames(session, ticker)
    if price_df.empty:
        return {"flow_window": flow_window, "horizons": list(horizons), "groups": {}}
    return flow_return_profile(
        price_df,
        flow_df,
        [g.value for g in MVP_INVESTOR_GROUPS],
        flow_window=flow_window,
        horizons=horizons,
    )
