"""Market-level aggregates and the benchmark series.

The benchmark prefers the **real market index** (``fact_index_daily``, e.g. the
KOSPI index ``1001``) when it has been ingested. If no index data is present it
falls back to a market-cap-weighted average of daily stock returns across the
ingested universe (the "proxy"). Use :func:`benchmark_return_series` /
:func:`benchmark_index_level` rather than the proxy functions directly so the
real index is used automatically once available.
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from kospi_flow.core.config import get_settings
from kospi_flow.core.models import FactIndexDaily, FactPriceDaily


def load_price_panel(session: Session, tickers: list[str] | None = None) -> pd.DataFrame:
    """Return a long price panel with columns date, ticker, close, market_cap,
    return_1d, trading_value, shares_outstanding."""
    stmt = select(
        FactPriceDaily.date,
        FactPriceDaily.ticker,
        FactPriceDaily.close,
        FactPriceDaily.market_cap,
        FactPriceDaily.return_1d,
        FactPriceDaily.trading_value,
        FactPriceDaily.shares_outstanding,
    )
    if tickers:
        stmt = stmt.where(FactPriceDaily.ticker.in_(tickers))
    rows = session.execute(stmt).all()
    return pd.DataFrame(
        rows,
        columns=[
            "date",
            "ticker",
            "close",
            "market_cap",
            "return_1d",
            "trading_value",
            "shares_outstanding",
        ],
    )


def market_return_series(price_panel: pd.DataFrame) -> pd.Series:
    """Cap-weighted average daily return per date (KOSPI proxy).

    Indexed by date. Uses each row's own ``market_cap`` as the weight; rows with
    missing return or market cap are ignored for that date.
    """
    if price_panel.empty:
        return pd.Series(dtype=float)
    df = price_panel.dropna(subset=["return_1d", "market_cap"]).copy()
    if df.empty:
        return pd.Series(dtype=float)

    def _wavg(group: pd.DataFrame) -> float:
        w = group["market_cap"].to_numpy()
        r = group["return_1d"].to_numpy()
        total = w.sum()
        return float((w * r).sum() / total) if total else float(r.mean())

    return (
        df.groupby("date", group_keys=False)[["market_cap", "return_1d"]]
        .apply(_wavg)
        .sort_index()
    )


def market_cumulative_return(price_panel: pd.DataFrame) -> pd.Series:
    """Cumulative market return from the cap-weighted daily series."""
    daily = market_return_series(price_panel)
    return (1.0 + daily).cumprod() - 1.0


def market_index_level(price_panel: pd.DataFrame, base: float = 1000.0) -> pd.Series:
    """Synthetic KOSPI-proxy index level (base=1000), indexed by date."""
    daily = market_return_series(price_panel)
    if daily.empty:
        return daily
    return base * (1.0 + daily).cumprod()


# --- Real index series (fact_index_daily) ---------------------------------


def _resolve_index_code(index_code: str | None) -> str:
    return index_code or get_settings().benchmark_index_code


def load_index_series(session: Session, index_code: str | None = None) -> pd.DataFrame:
    """Return the index OHLC frame (date, close, return_1d) for ``index_code``."""
    code = _resolve_index_code(index_code)
    rows = session.execute(
        select(FactIndexDaily.date, FactIndexDaily.close, FactIndexDaily.return_1d)
        .where(FactIndexDaily.index_code == code)
        .order_by(FactIndexDaily.date)
    ).all()
    return pd.DataFrame(rows, columns=["date", "close", "return_1d"])


def has_index(session: Session, index_code: str | None = None) -> bool:
    """True if any index rows exist for ``index_code``."""
    code = _resolve_index_code(index_code)
    return session.execute(
        select(FactIndexDaily.date).where(FactIndexDaily.index_code == code).limit(1)
    ).first() is not None


def index_return_series(session: Session, index_code: str | None = None) -> pd.Series:
    """Daily index returns indexed by date (uses stored return_1d, else close)."""
    df = load_index_series(session, index_code)
    if df.empty:
        return pd.Series(dtype=float)
    s = df.set_index("date")
    ret = s["return_1d"]
    if ret.isna().all():
        ret = s["close"].pct_change()
    return ret.dropna().sort_index()


def index_level_series(session: Session, index_code: str | None = None) -> pd.Series:
    """Index close level indexed by date."""
    df = load_index_series(session, index_code)
    if df.empty:
        return pd.Series(dtype=float)
    return df.set_index("date")["close"].sort_index()


# --- Benchmark: real index preferred, proxy fallback ----------------------


def benchmark_source(session: Session, index_code: str | None = None) -> str:
    """``"index:<code>"`` if real index data exists, else ``"proxy"``."""
    code = _resolve_index_code(index_code)
    return f"index:{code}" if has_index(session, code) else "proxy"


def benchmark_return_series(
    session: Session, index_code: str | None = None
) -> pd.Series:
    """Daily benchmark returns: real index if present, else cap-weighted proxy."""
    if has_index(session, index_code):
        return index_return_series(session, index_code)
    return market_return_series(load_price_panel(session))


def benchmark_index_level(
    session: Session, index_code: str | None = None, base: float = 1000.0
) -> pd.Series:
    """Benchmark level series: real index close if present, else proxy level."""
    if has_index(session, index_code):
        return index_level_series(session, index_code)
    return market_index_level(load_price_panel(session), base=base)
