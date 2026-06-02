"""Phase 3 analytics: labels, correlation, events, similar cases."""

from __future__ import annotations

import numpy as np
import pandas as pd

from kospi_flow.analytics.correlation import flow_forward_correlation
from kospi_flow.analytics.events import detect_events, event_study
from kospi_flow.analytics.labels import (
    add_forward_returns,
    forward_return_close_to_close,
    forward_simple_return,
    outperform_market,
)
from kospi_flow.analytics.profile import flow_return_profile, monotonicity
from kospi_flow.analytics.similar import find_similar_cases


def _price(n=300, start=100.0, drift=0.001):
    dates = pd.bdate_range("2021-01-04", periods=n)
    close = start * np.exp(np.cumsum(np.full(n, drift)))
    return pd.DataFrame(
        {
            "date": [d.date() for d in dates],
            "open": close * 0.999,
            "close": close,
            "adj_close": close,
            "market_cap": close * 1e9,
        }
    )


def test_forward_return_no_lookahead_tail_is_nan():
    s = pd.Series([1.0, 2.0, 4.0, 8.0])
    out = forward_return_close_to_close(s, 1)
    assert np.isnan(out.iloc[-1])  # last row has no future value
    assert abs(out.iloc[0] - np.log(2)) < 1e-9


def test_forward_simple_return_value():
    close = pd.Series([100.0, 110.0, 121.0])
    out = forward_simple_return(close, 1)
    assert abs(out.iloc[0] - 0.1) < 1e-9
    assert np.isnan(out.iloc[-1])


def test_outperform_market_label():
    stock = pd.Series([0.05, -0.02, np.nan])
    mkt = pd.Series([0.01, 0.01, 0.01])
    out = outperform_market(stock, mkt)
    assert out.iloc[0] == 1.0
    assert out.iloc[1] == 0.0
    assert np.isnan(out.iloc[2])


def test_add_forward_returns_columns():
    df = add_forward_returns(_price(50), horizons=(1, 5))
    for col in ["fwd_ret_close_1", "fwd_ret_simple_5", "fwd_ret_trade_1"]:
        assert col in df.columns


def test_correlation_runs_and_counts():
    price = _price(120)
    dates = price["date"]
    # Construct flow that leads returns: positive net buy before up days.
    flow = pd.DataFrame(
        {
            "date": list(dates) * 1,
            "investor_group": ["foreign"] * len(dates),
            "net_buy_amount": np.linspace(-1e9, 1e9, len(dates)),
        }
    )
    res = flow_forward_correlation(price, flow, "foreign", flow_window=5, horizon=5)
    assert res.n > 50
    assert res.investor_group == "foreign"
    assert res.pearson is None or -1.0 <= res.pearson <= 1.0


def test_detect_and_study_events():
    price = _price(300)
    dates = price["date"]
    rng = np.random.RandomState(0)
    rows = []
    for g, scale in [("foreign", 5e9), ("institution", 4e9), ("retail", 3e9)]:
        rows.append(
            pd.DataFrame(
                {
                    "date": dates,
                    "investor_group": g,
                    "net_buy_amount": rng.normal(0, scale, len(dates)),
                }
            )
        )
    flow = pd.concat(rows, ignore_index=True)

    flag = detect_events(price, flow, "foreign_accumulation")
    assert flag.dtype == bool
    assert len(flag) == len(price)

    results, matching = event_study(price, flow, "foreign_accumulation")
    by_h = {r.horizon: r for r in results}
    assert set(by_h) == {1, 3, 5, 10, 20}
    # At least some events should be detected on 300 days of data.
    assert len(matching) >= 1
    for r in results:
        if r.count:
            assert r.worst_case <= r.median_return <= r.best_case


def test_flow_return_profile_structure_and_buckets():
    price = _price(300)
    dates = price["date"]
    rng = np.random.RandomState(1)
    rows = []
    for g in ("foreign", "institution", "retail"):
        rows.append(
            pd.DataFrame(
                {
                    "date": dates,
                    "investor_group": g,
                    "net_buy_amount": rng.normal(0, 5e9, len(dates)),
                }
            )
        )
    flow = pd.concat(rows, ignore_index=True)

    prof = flow_return_profile(
        price, flow, ["foreign", "institution", "retail"], flow_window=5
    )
    assert prof["flow_window"] == 5 and prof["n_buckets"] == 5
    fg = prof["groups"]["foreign"]["quintiles"]
    assert len(fg) == 5
    # Quintiles are ordered by trailing net-buy strength (Q1 lowest → Q5 highest).
    means = [q["flow_pct_mcap_mean"] for q in fg]
    assert means == sorted(means)
    # Each quintile carries forward-return stats for every horizon.
    for q in fg:
        assert set(q["mean_return"]) == {"1", "3", "5", "10", "20"}
        assert q["n"] > 0
    m = monotonicity(fg, 5)
    assert m is None or (-1.0 <= m <= 1.0)


def test_flow_return_profile_detects_monotonic_relationship():
    # Construct flow that increases over time and a price that rises faster later,
    # so higher trailing buying lines up with higher subsequent returns.
    n = 300
    dates = pd.bdate_range("2021-01-04", periods=n)
    drift = np.linspace(-0.002, 0.004, n)  # later days trend up harder
    close = 100.0 * np.exp(np.cumsum(drift))
    price = pd.DataFrame(
        {
            "date": [d.date() for d in dates],
            "open": close * 0.999,
            "close": close,
            "adj_close": close,
            "market_cap": 1e12,
        }
    )
    flow = pd.DataFrame(
        {
            "date": [d.date() for d in dates],
            "investor_group": "foreign",
            "net_buy_amount": np.linspace(-1e10, 1e10, n),  # buying ramps up over time
        }
    )
    prof = flow_return_profile(price, flow, ["foreign"], flow_window=5)
    m = monotonicity(prof["groups"]["foreign"]["quintiles"], 5)
    assert m is not None and m > 0.5  # stronger buying → higher forward return


def test_similar_cases_excludes_future():
    price = _price(60)
    feats = pd.DataFrame(
        {"date": price["date"], "f1": np.arange(60.0), "f2": np.arange(60.0) % 5}
    )
    outcome = forward_simple_return(price["close"], 5)
    cases = find_similar_cases(feats, ["f1", "f2"], outcome, reference_index=40, k=5)
    assert len(cases) == 5
    # All matched dates must be strictly before the reference date.
    ref_date = price["date"].iloc[40].isoformat()
    assert all(c["date"] < ref_date for c in cases)
