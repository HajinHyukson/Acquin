"""ML training-dataset builder (context doc §11.2).

Builds a panel of (date, ticker) rows with investor-flow + price/market features
and forward-return targets. All features use data up to and including day ``t``;
targets are strictly forward. The same builder is used at training and inference
time so features cannot drift between the two.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from kospi_flow.analytics.features import rolling_net_buy, signed_streak, zscore
from kospi_flow.analytics.labels import forward_return_close_to_close, outperform_market
from kospi_flow.analytics.market import benchmark_index_level
from kospi_flow.core.enums import MVP_INVESTOR_GROUPS
from kospi_flow.core.models import FactInvestorFlowDaily, FactPriceDaily

FEATURE_VERSION = "ml_v0"
_GROUPS = [g.value for g in MVP_INVESTOR_GROUPS]
_NON_FEATURE_COLS = {"date", "ticker", "y_reg", "y_cls", "close_price"}


def _load_prices(session: Session, tickers: list[str] | None) -> pd.DataFrame:
    stmt = select(
        FactPriceDaily.date,
        FactPriceDaily.ticker,
        FactPriceDaily.close,
        FactPriceDaily.adj_close,
        FactPriceDaily.market_cap,
        FactPriceDaily.trading_value,
    )
    if tickers:
        stmt = stmt.where(FactPriceDaily.ticker.in_(tickers))
    rows = session.execute(stmt).all()
    return pd.DataFrame(
        rows,
        columns=["date", "ticker", "close", "adj_close", "market_cap", "trading_value"],
    )


def _load_flows(session: Session, tickers: list[str] | None) -> pd.DataFrame:
    stmt = select(
        FactInvestorFlowDaily.date,
        FactInvestorFlowDaily.ticker,
        FactInvestorFlowDaily.investor_group,
        FactInvestorFlowDaily.net_buy_amount,
    )
    if tickers:
        stmt = stmt.where(FactInvestorFlowDaily.ticker.in_(tickers))
    rows = session.execute(stmt).all()
    return pd.DataFrame(
        rows, columns=["date", "ticker", "investor_group", "net_buy_amount"]
    )


def _stock_features(price: pd.DataFrame, flows: pd.DataFrame) -> pd.DataFrame:
    """Per-stock feature frame (price sorted ascending by date)."""
    p = price.sort_values("date").reset_index(drop=True)
    close = p["close"]
    mcap = p["market_cap"].replace(0, np.nan)
    ret1 = close.pct_change()

    feat = pd.DataFrame({"date": p["date"]})
    feat["close_price"] = close
    feat["ret_1d"] = ret1
    feat["ret_5d"] = close.pct_change(5)
    feat["ret_20d"] = close.pct_change(20)
    feat["vol_20d"] = ret1.rolling(20, min_periods=10).std(ddof=0)
    feat["dist_20dma"] = close / close.rolling(20, min_periods=5).mean() - 1.0
    feat["turnover_20d"] = p["trading_value"].rolling(20, min_periods=5).mean() / mcap

    wide = flows.pivot_table(
        index="date", columns="investor_group", values="net_buy_amount", aggfunc="sum"
    ).reindex(p["date"].to_numpy())
    for g in _GROUPS:
        s = (
            wide[g].reset_index(drop=True).fillna(0.0)
            if g in wide.columns
            else pd.Series(np.zeros(len(p)))
        )
        feat[f"net5_{g}"] = rolling_net_buy(s, 5)
        feat[f"net20_{g}"] = rolling_net_buy(s, 20)
        feat[f"net5_pct_mcap_{g}"] = rolling_net_buy(s, 5) / mcap
        feat[f"streak_{g}"] = signed_streak(s).astype(float)
        feat[f"z60_{g}"] = zscore(s, 60)
    return feat


def build_panel(
    session: Session, horizon: int, tickers: list[str] | None = None
) -> tuple[pd.DataFrame, list[str]]:
    """Full panel with features + targets; targets are NaN in the forward tail.

    Returns (panel, feature_cols). Use :func:`build_dataset` for training (drops
    target NaNs) and :func:`latest_feature_rows` for inference.
    """
    prices = _load_prices(session, tickers)
    if prices.empty:
        return pd.DataFrame(), []
    flows = _load_flows(session, tickers)
    # Benchmark for the outperformance label: real index if ingested, else proxy.
    level = benchmark_index_level(session)

    panels: list[pd.DataFrame] = []
    feature_cols: list[str] | None = None
    for ticker, pg in prices.groupby("ticker"):
        pg = pg.sort_values("date").reset_index(drop=True)
        fg = flows[flows["ticker"] == ticker]
        feat = _stock_features(pg, fg)

        feat["y_reg"] = forward_return_close_to_close(pg["adj_close"], horizon)
        stock_fwd = pg["close"].shift(-horizon) / pg["close"] - 1.0
        mkt_aligned = level.reindex(pg["date"].to_numpy()).reset_index(drop=True)
        mkt_fwd = mkt_aligned.shift(-horizon) / mkt_aligned - 1.0
        feat["y_cls"] = outperform_market(stock_fwd, mkt_fwd)

        feat["mkt_ret_5d"] = (mkt_aligned / mkt_aligned.shift(5) - 1.0).to_numpy()
        feat["stock_minus_mkt_5d"] = feat["ret_5d"] - feat["mkt_ret_5d"]

        feat.insert(1, "ticker", ticker)
        if feature_cols is None:
            feature_cols = [c for c in feat.columns if c not in _NON_FEATURE_COLS]
        panels.append(feat)

    panel = pd.concat(panels, ignore_index=True)
    return panel, (feature_cols or [])


def build_dataset(
    session: Session, horizon: int, tickers: list[str] | None = None
) -> tuple[pd.DataFrame, list[str]]:
    """Training panel: rows with a known forward target only (no look-ahead)."""
    panel, feature_cols = build_panel(session, horizon, tickers)
    if panel.empty:
        return panel, feature_cols
    panel = panel.dropna(subset=["y_reg", "y_cls"]).reset_index(drop=True)
    return panel, feature_cols


def latest_feature_rows(
    session: Session, tickers: list[str] | None = None
) -> tuple[pd.DataFrame, list[str]]:
    """Most recent feature row per ticker (for inference; target may be NaN)."""
    panel, feature_cols = build_panel(session, horizon=1, tickers=tickers)
    if panel.empty:
        return panel, feature_cols
    latest = (
        panel.sort_values("date").groupby("ticker", as_index=False).tail(1)
        .reset_index(drop=True)
    )
    return latest, feature_cols
