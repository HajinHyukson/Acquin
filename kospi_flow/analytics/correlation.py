"""Correlation between investor flow and subsequent returns (context doc §11.3).

Transparent statistics computed before any ML: for a stock, correlate trailing
net-buy (normalized by market cap) with forward returns at several horizons.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from kospi_flow.analytics.features import rolling_net_buy
from kospi_flow.analytics.labels import HORIZONS, forward_simple_return


@dataclass
class CorrelationResult:
    investor_group: str
    flow_window: int
    horizon: int
    n: int
    pearson: float | None
    spearman: float | None

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def _safe_corr(x: np.ndarray, y: np.ndarray) -> tuple[float | None, float | None]:
    if len(x) < 3 or np.std(x) == 0 or np.std(y) == 0:
        return None, None
    pear = float(stats.pearsonr(x, y).statistic)
    spear = float(stats.spearmanr(x, y).statistic)
    return pear, spear


def flow_forward_correlation(
    price_df: pd.DataFrame,
    flow_df: pd.DataFrame,
    investor_group: str,
    flow_window: int,
    horizon: int,
) -> CorrelationResult:
    """Correlate trailing net-buy %mcap with forward simple return for a stock.

    ``price_df``: date, close, market_cap (sorted or not).
    ``flow_df``: date, investor_group, net_buy_amount.
    """
    price = price_df.sort_values("date").reset_index(drop=True)
    grp = flow_df[flow_df["investor_group"] == investor_group]
    merged = price.merge(
        grp[["date", "net_buy_amount"]], on="date", how="left"
    )
    merged["net_buy_amount"] = merged["net_buy_amount"].fillna(0.0)

    trailing = rolling_net_buy(merged["net_buy_amount"], flow_window)
    pct_mcap = (trailing / merged["market_cap"].replace(0, np.nan)).to_numpy()
    fwd = forward_simple_return(merged["close"], horizon).to_numpy()

    mask = ~(np.isnan(pct_mcap) | np.isnan(fwd))
    x, y = pct_mcap[mask], fwd[mask]
    pear, spear = _safe_corr(x, y)
    return CorrelationResult(
        investor_group=investor_group,
        flow_window=flow_window,
        horizon=horizon,
        n=int(mask.sum()),
        pearson=pear,
        spearman=spear,
    )


def correlation_grid(
    price_df: pd.DataFrame,
    flow_df: pd.DataFrame,
    investor_groups: list[str],
    flow_windows: tuple[int, ...] = (5, 20),
    horizons: tuple[int, ...] = HORIZONS,
) -> list[CorrelationResult]:
    """Compute correlations across groups × windows × horizons."""
    out: list[CorrelationResult] = []
    for g in investor_groups:
        for w in flow_windows:
            for h in horizons:
                out.append(flow_forward_correlation(price_df, flow_df, g, w, h))
    return out
