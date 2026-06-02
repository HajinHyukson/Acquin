"""Event definitions and event-study engine (context doc §10).

Given a stock's price + investor-flow history, detect signal dates and measure
the distribution of subsequent returns (and outperformance vs. the KOSPI proxy)
at multiple horizons. No look-ahead: events use only data up to the event date;
outcomes use strictly forward returns.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from kospi_flow.analytics.features import rolling_net_buy
from kospi_flow.analytics.labels import HORIZONS, forward_simple_return

EVENT_TYPES = (
    "foreign_accumulation",
    "institution_accumulation",
    "dual_accumulation",
    "retail_exit",
    "price_flow_divergence",
)


def _wide_flows(flow_df: pd.DataFrame, dates: pd.Series) -> pd.DataFrame:
    """Pivot net_buy_amount to wide (one column per group), aligned to dates."""
    wide = flow_df.pivot_table(
        index="date", columns="investor_group", values="net_buy_amount", aggfunc="sum"
    ).reindex(dates.to_numpy())
    for g in ("foreign", "institution", "retail"):
        if g not in wide.columns:
            wide[g] = 0.0
    return wide.reset_index(drop=True).fillna(0.0)


def detect_events(
    price_df: pd.DataFrame, flow_df: pd.DataFrame, event_type: str
) -> pd.Series:
    """Boolean Series (indexed like sorted price_df) flagging event dates."""
    price = price_df.sort_values("date").reset_index(drop=True)
    flows = _wide_flows(flow_df, price["date"])
    foreign, inst, retail = flows["foreign"], flows["institution"], flows["retail"]
    mcap = price["market_cap"].replace(0, np.nan)
    close = price["close"]

    if event_type == "foreign_accumulation":
        net5 = rolling_net_buy(foreign, 5)
        # Top-decile vs the stock's own trailing 252D distribution of 5D net buy.
        thresh = net5.rolling(252, min_periods=60).quantile(0.9)
        flag = (net5 >= thresh) & thresh.notna()
    elif event_type == "institution_accumulation":
        net10_pct = rolling_net_buy(inst, 10) / mcap
        flag = net10_pct >= 0.005
    elif event_type == "dual_accumulation":
        both = (foreign > 0) & (inst > 0)
        # 3+ consecutive days of both buying.
        run = both & both.shift(1).fillna(False) & both.shift(2).fillna(False)
        flag = run
    elif event_type == "retail_exit":
        flag = (retail < 0) & ((foreign > 0) | (inst > 0))
    elif event_type == "price_flow_divergence":
        trailing_ret5 = close / close.shift(5) - 1.0
        accumulating = (rolling_net_buy(foreign, 5) > 0) | (rolling_net_buy(inst, 5) > 0)
        flag = (trailing_ret5 < 0) & accumulating
    else:
        raise ValueError(f"Unknown event_type '{event_type}'")

    return flag.fillna(False).astype(bool)


@dataclass
class EventStudyResult:
    event_type: str
    horizon: int
    count: int
    mean_return: float | None
    median_return: float | None
    positive_return_rate: float | None
    outperform_kospi_rate: float | None
    p10_return: float | None
    p90_return: float | None
    best_case: float | None
    worst_case: float | None

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def event_study(
    price_df: pd.DataFrame,
    flow_df: pd.DataFrame,
    event_type: str,
    market_fwd: dict[int, pd.Series] | None = None,
    horizons: tuple[int, ...] = HORIZONS,
) -> tuple[list[EventStudyResult], list[str]]:
    """Run an event study; return per-horizon stats and the matching dates.

    ``market_fwd`` optionally maps horizon -> market forward simple return Series
    aligned to the stock's sorted dates, enabling outperformance rates.
    """
    price = price_df.sort_values("date").reset_index(drop=True)
    flag = detect_events(price, flow_df, event_type)
    results: list[EventStudyResult] = []

    for h in horizons:
        fwd = forward_simple_return(price["close"], h)
        sample = fwd[flag & fwd.notna()]
        vals = sample.to_numpy()
        if len(vals) == 0:
            results.append(
                EventStudyResult(event_type, h, 0, *([None] * 8))
            )
            continue
        outperf_rate = None
        if market_fwd is not None and h in market_fwd:
            mkt = market_fwd[h]
            diff = (fwd - mkt)[flag & fwd.notna() & mkt.notna()]
            if len(diff):
                outperf_rate = float((diff > 0).mean())
        results.append(
            EventStudyResult(
                event_type=event_type,
                horizon=h,
                count=int(len(vals)),
                mean_return=float(np.mean(vals)),
                median_return=float(np.median(vals)),
                positive_return_rate=float((vals > 0).mean()),
                outperform_kospi_rate=outperf_rate,
                p10_return=float(np.percentile(vals, 10)),
                p90_return=float(np.percentile(vals, 90)),
                best_case=float(np.max(vals)),
                worst_case=float(np.min(vals)),
            )
        )

    matching_dates = [
        d.isoformat() for d in price.loc[flag, "date"].tolist()
    ]
    return results, matching_dates
