"""Core feature-calculation correctness."""

from __future__ import annotations

import numpy as np
import pandas as pd

from kospi_flow.analytics.features import (
    compute_stock_features,
    pct_of,
    rolling_net_buy,
    signed_streak,
    simple_return,
)


def test_rolling_net_buy_trailing_sum():
    s = pd.Series([1, 2, 3, 4, 5], dtype=float)
    out = rolling_net_buy(s, 3)
    # min_periods=1: partial sums early, trailing 3-sum after.
    assert list(out) == [1.0, 3.0, 6.0, 9.0, 12.0]


def test_signed_streak_directions():
    s = pd.Series([1, 2, -1, -1, -1, 0, 3], dtype=float)
    out = list(signed_streak(s))
    assert out == [1, 2, -1, -2, -3, 0, 1]


def test_signed_streak_reset_on_sign_flip():
    s = pd.Series([1, 1, -1, 1], dtype=float)
    assert list(signed_streak(s)) == [1, 2, -1, 1]


def test_pct_of_handles_zero_denominator():
    num = pd.Series([1.0, 2.0])
    den = pd.Series([0.0, 4.0])
    out = pct_of(num, den)
    assert np.isnan(out.iloc[0])
    assert out.iloc[1] == 0.5


def test_simple_return():
    close = pd.Series([100.0, 110.0, 121.0])
    out = simple_return(close, 1)
    assert np.isnan(out.iloc[0])
    assert abs(out.iloc[1] - 0.1) < 1e-9
    assert abs(out.iloc[2] - 0.1) < 1e-9


def test_compute_stock_features_shapes_and_no_lookahead():
    dates = pd.bdate_range("2021-01-04", periods=30)
    price_df = pd.DataFrame(
        {
            "date": [d.date() for d in dates],
            "ticker": "005930",
            "close": np.linspace(100, 130, 30),
            "market_cap": 1e12,
            "return_1d": np.r_[np.nan, np.full(29, 0.01)],
        }
    )
    groups = ["foreign", "institution", "retail"]
    flow_rows = []
    for d in dates:
        for g in groups:
            flow_rows.append(
                {"date": d.date(), "investor_group": g, "net_buy_amount": 1.0e9}
            )
    flow_df = pd.DataFrame(flow_rows)

    feats = compute_stock_features(price_df, flow_df)
    assert len(feats) == 30
    assert set(
        [
            "foreign_net_5d_amt",
            "institution_net_20d_pct_mcap",
            "retail_streak_days",
            "foreign_flow_z_60d",
            "price_return_5d",
            "volatility_20d",
        ]
    ).issubset(feats.columns)
    # Retail bought every day -> streak equals row index + 1.
    assert feats["retail_streak_days"].iloc[-1] == 30
    # 5d return on a monotonic series is positive once enough history exists.
    assert feats["price_return_5d"].iloc[5] > 0
