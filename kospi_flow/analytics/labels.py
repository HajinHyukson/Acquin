"""Forward-return label generation (context doc §11.1).

All labels are forward-looking and therefore NaN at the tail of the series
(no future data) — never backfilled. Computed on a per-stock price frame sorted
ascending by date.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

HORIZONS = (1, 3, 5, 10, 20)


def forward_return_close_to_close(adj_close: pd.Series, h: int) -> pd.Series:
    """Analytical target: log(adj_close[t+h] / adj_close[t])."""
    future = adj_close.shift(-h)
    return np.log(future / adj_close)


def forward_return_tradeable(
    adj_close: pd.Series, open_: pd.Series, h: int
) -> pd.Series:
    """Tradeable target: log(adj_close[t+h] / open[t+1]).

    Investor-flow data is known only after the close, so the earliest realistic
    entry is the next session's open. Used for backtesting (context doc §11.1).
    """
    entry = open_.shift(-1)
    exit_ = adj_close.shift(-h)
    return np.log(exit_ / entry)


def forward_simple_return(close: pd.Series, h: int) -> pd.Series:
    """Simple forward return close[t+h]/close[t] - 1 (for display/event study)."""
    return close.shift(-h) / close - 1.0


def outperform_market(
    stock_fwd_return: pd.Series, market_fwd_return: pd.Series
) -> pd.Series:
    """1 where the stock's forward return beats the market's, else 0 (NaN-safe)."""
    diff = stock_fwd_return - market_fwd_return
    return diff.where(diff.isna(), (diff > 0).astype(float))


def add_forward_returns(
    price_df: pd.DataFrame,
    horizons: tuple[int, ...] = HORIZONS,
    price_col: str = "adj_close",
) -> pd.DataFrame:
    """Return ``price_df`` (sorted by date) with fwd return columns per horizon.

    Adds ``fwd_ret_close_{h}`` (log close-to-close) and ``fwd_ret_simple_{h}``.
    If ``open`` is present, also adds ``fwd_ret_trade_{h}``.
    """
    df = price_df.sort_values("date").reset_index(drop=True).copy()
    close = df[price_col]
    for h in horizons:
        df[f"fwd_ret_close_{h}"] = forward_return_close_to_close(close, h)
        df[f"fwd_ret_simple_{h}"] = forward_simple_return(df["close"], h)
        if "open" in df.columns:
            df[f"fwd_ret_trade_{h}"] = forward_return_tradeable(close, df["open"], h)
    return df
