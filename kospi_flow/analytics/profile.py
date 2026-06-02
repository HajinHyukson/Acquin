"""Forward-return-by-buying-strength profile (quintile analysis).

The most legible view of the flow→price relationship: bucket each investor
group's trailing net-buy (% of market cap) into quintiles and report the average
*subsequent* return per bucket and horizon. If buying pressure leads price for a
stock, the mean forward return should rise from Q1 (강한 순매도) to Q5 (강한 순매수).

No look-ahead: buckets are defined by trailing flow at day t; returns are strictly
forward (t→t+h).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from kospi_flow.analytics.features import rolling_net_buy
from kospi_flow.analytics.labels import HORIZONS, forward_simple_return


def flow_return_profile(
    price_df: pd.DataFrame,
    flow_df: pd.DataFrame,
    groups: list[str],
    flow_window: int = 5,
    horizons: tuple[int, ...] = HORIZONS,
    n_buckets: int = 5,
) -> dict:
    """Return per-group quintile stats of forward return vs trailing net-buy %mcap.

    ``price_df``: columns date, close, market_cap (sorted or not).
    ``flow_df``: columns date, investor_group, net_buy_amount.
    """
    price = price_df.sort_values("date").reset_index(drop=True)
    close = price["close"]
    mcap = price["market_cap"].replace(0, np.nan)
    fwd = {h: forward_simple_return(close, h).to_numpy() for h in horizons}

    wide = flow_df.pivot_table(
        index="date", columns="investor_group", values="net_buy_amount", aggfunc="sum"
    ).reindex(price["date"].to_numpy())

    out: dict = {
        "flow_window": flow_window,
        "horizons": list(horizons),
        "n_buckets": n_buckets,
        "groups": {},
    }

    for g in groups:
        s = (
            wide[g].reset_index(drop=True).fillna(0.0)
            if g in wide.columns
            else pd.Series(np.zeros(len(price)))
        )
        pct = (rolling_net_buy(s, flow_window) / mcap).to_numpy()
        df = pd.DataFrame({"pct": pct})
        for h in horizons:
            df[f"r{h}"] = fwd[h]
        df = df[np.isfinite(df["pct"])].reset_index(drop=True)

        if len(df) < n_buckets * 3 or df["pct"].nunique() < n_buckets:
            out["groups"][g] = {"quintiles": [], "note": "insufficient data"}
            continue

        # Rank-based buckets so ties don't break qcut; Q1=lowest, Q5=highest.
        df["q"] = pd.qcut(
            df["pct"].rank(method="first"), n_buckets, labels=False
        ) + 1

        quintiles = []
        for q in range(1, n_buckets + 1):
            sub = df[df["q"] == q]
            entry: dict = {
                "quintile": q,
                "n": int(len(sub)),
                "flow_pct_mcap_mean": float(sub["pct"].mean()),
                "flow_pct_mcap_min": float(sub["pct"].min()),
                "flow_pct_mcap_max": float(sub["pct"].max()),
                "mean_return": {},
                "median_return": {},
                "hit_rate": {},
            }
            for h in horizons:
                vals = sub[f"r{h}"].to_numpy()
                vals = vals[np.isfinite(vals)]
                if len(vals):
                    entry["mean_return"][str(h)] = float(np.mean(vals))
                    entry["median_return"][str(h)] = float(np.median(vals))
                    entry["hit_rate"][str(h)] = float((vals > 0).mean())
                else:
                    entry["mean_return"][str(h)] = None
                    entry["median_return"][str(h)] = None
                    entry["hit_rate"][str(h)] = None
            quintiles.append(entry)
        out["groups"][g] = {"quintiles": quintiles}

    return out


def monotonicity(quintiles: list[dict], horizon: int) -> float | None:
    """Spearman rank corr between quintile index and mean forward return.

    +1 means returns rise monotonically with buying strength (buying leads price);
    -1 means the opposite (contrarian). Returns None if not computable.
    """
    if not quintiles:
        return None
    from scipy import stats

    qs, rs = [], []
    for e in quintiles:
        r = e["mean_return"].get(str(horizon))
        if r is not None:
            qs.append(e["quintile"])
            rs.append(r)
    if len(qs) < 3 or np.std(rs) == 0:
        return None
    return float(stats.spearmanr(qs, rs).statistic)
