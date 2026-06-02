"""Core feature calculations.

Pure, well-tested functions plus a convenience builder that produces
``fact_features_daily`` rows from price and investor-flow frames. These mirror
the rolling-trend and normalization features in the context doc (sections 10
and 11) but kept to a small, transparent MVP subset.

All functions avoid look-ahead: a value at row ``t`` uses only data up to and
including ``t`` (context doc, section 11.5).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

FEATURE_VERSION = "v0"


def rolling_net_buy(net_buy: pd.Series, window: int) -> pd.Series:
    """Trailing sum of net buy over ``window`` rows (inclusive of current).

    Uses ``min_periods=1`` so early rows return the partial sum rather than NaN.
    """
    return net_buy.rolling(window=window, min_periods=1).sum()


def signed_streak(net_buy: pd.Series) -> pd.Series:
    """Signed consecutive-day streak.

    Positive = consecutive net-buy days, negative = consecutive net-sell days,
    0 when the value is exactly 0 (or resets the streak). The streak at row
    ``t`` counts the run ending at ``t``.
    """
    values = net_buy.fillna(0.0).to_numpy()
    out = np.zeros(len(values), dtype=int)
    streak = 0
    for i, v in enumerate(values):
        if v > 0:
            streak = streak + 1 if streak > 0 else 1
        elif v < 0:
            streak = streak - 1 if streak < 0 else -1
        else:
            streak = 0
        out[i] = streak
    return pd.Series(out, index=net_buy.index)


def zscore(series: pd.Series, window: int) -> pd.Series:
    """Trailing rolling z-score over ``window`` rows.

    Returns NaN where the trailing standard deviation is 0 or undefined.
    """
    roll = series.rolling(window=window, min_periods=max(2, window // 2))
    mean = roll.mean()
    std = roll.std(ddof=0)
    z = (series - mean) / std
    return z.where(std > 0)


def pct_of(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Safe elementwise ratio; division by 0/NaN yields NaN."""
    denom = denominator.replace(0, np.nan)
    return numerator / denom


def simple_return(close: pd.Series, periods: int) -> pd.Series:
    """Trailing simple return over ``periods`` rows: close[t]/close[t-p] - 1."""
    return close.pct_change(periods=periods)


def volatility(returns: pd.Series, window: int) -> pd.Series:
    """Trailing standard deviation of daily returns over ``window`` rows."""
    return returns.rolling(window=window, min_periods=max(2, window // 2)).std(ddof=0)


def compute_stock_features(
    price_df: pd.DataFrame,
    flow_df: pd.DataFrame,
    feature_version: str = FEATURE_VERSION,
) -> pd.DataFrame:
    """Build a per-date feature frame for one stock.

    Parameters
    ----------
    price_df:
        Columns: ``date``, ``ticker``, ``close``, ``market_cap``, ``return_1d``.
        One row per trading date, sorted or unsorted.
    flow_df:
        Columns: ``date``, ``investor_group``, ``net_buy_amount``.
        Long format across investor groups.

    Returns a frame keyed by ``date``/``ticker``/``feature_version`` with the
    MVP feature columns of ``fact_features_daily``.
    """
    if price_df.empty:
        return pd.DataFrame()

    price = price_df.sort_values("date").reset_index(drop=True).copy()
    ticker = price["ticker"].iloc[0]

    # Pivot flows to wide: one column of net_buy_amount per investor group.
    flows_wide = (
        flow_df.pivot_table(
            index="date",
            columns="investor_group",
            values="net_buy_amount",
            aggfunc="sum",
        )
        .reindex(price["date"].to_numpy())
    )

    def group_series(name: str) -> pd.Series:
        if name in flows_wide.columns:
            return flows_wide[name].reset_index(drop=True).fillna(0.0)
        return pd.Series(np.zeros(len(price)), index=price.index)

    foreign = group_series("foreign")
    institution = group_series("institution")
    retail = group_series("retail")

    close = price["close"].reset_index(drop=True)
    mcap = price.get("market_cap", pd.Series(np.nan, index=price.index)).reset_index(
        drop=True
    )
    ret_1d = price.get("return_1d")
    if ret_1d is None:
        ret_1d = close.pct_change()
    else:
        ret_1d = ret_1d.reset_index(drop=True)

    out = pd.DataFrame(
        {
            "date": price["date"].to_numpy(),
            "ticker": ticker,
            "feature_version": feature_version,
            "foreign_net_5d_amt": rolling_net_buy(foreign, 5),
            "institution_net_20d_pct_mcap": pct_of(
                rolling_net_buy(institution, 20), mcap
            ),
            "retail_streak_days": signed_streak(retail).astype(int),
            "foreign_flow_z_60d": zscore(foreign, 60),
            "price_return_5d": simple_return(close, 5),
            "volatility_20d": volatility(ret_1d, 20),
        }
    )
    return out
