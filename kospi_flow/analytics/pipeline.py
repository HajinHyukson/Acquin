"""Feature pipeline: read core tables, compute features, write fact_features_daily.

Bridges the pure functions in :mod:`kospi_flow.analytics.features` with the
database. Idempotent: re-running upserts on the feature primary key.
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import select

from kospi_flow.analytics.features import FEATURE_VERSION, compute_stock_features
from kospi_flow.core.db import Database
from kospi_flow.core.logging import get_logger
from kospi_flow.core.models import (
    FactFeaturesDaily,
    FactInvestorFlowDaily,
    FactPriceDaily,
)

logger = get_logger(__name__)


def _load_price(s, ticker: str) -> pd.DataFrame:
    rows = s.execute(
        select(
            FactPriceDaily.date,
            FactPriceDaily.ticker,
            FactPriceDaily.close,
            FactPriceDaily.market_cap,
            FactPriceDaily.return_1d,
        ).where(FactPriceDaily.ticker == ticker)
    ).all()
    return pd.DataFrame(
        rows, columns=["date", "ticker", "close", "market_cap", "return_1d"]
    )


def _load_flows(s, ticker: str) -> pd.DataFrame:
    rows = s.execute(
        select(
            FactInvestorFlowDaily.date,
            FactInvestorFlowDaily.investor_group,
            FactInvestorFlowDaily.net_buy_amount,
        ).where(FactInvestorFlowDaily.ticker == ticker)
    ).all()
    return pd.DataFrame(
        rows, columns=["date", "investor_group", "net_buy_amount"]
    )


def generate_features(
    database: Database,
    tickers: list[str] | None = None,
    feature_version: str = FEATURE_VERSION,
) -> int:
    """Compute and upsert features for ``tickers`` (all stocks if None).

    Returns the number of feature rows written.
    """
    written = 0
    with database.session() as s:
        if tickers is None:
            tickers = [
                t for (t,) in s.execute(
                    select(FactPriceDaily.ticker).distinct()
                ).all()
            ]
        for ticker in tickers:
            price_df = _load_price(s, ticker)
            if price_df.empty:
                logger.warning("[%s] no price rows; skipping features", ticker)
                continue
            flow_df = _load_flows(s, ticker)
            feats = compute_stock_features(price_df, flow_df, feature_version)
            for r in feats.itertuples(index=False):
                s.merge(
                    FactFeaturesDaily(
                        date=r.date,
                        ticker=r.ticker,
                        feature_version=r.feature_version,
                        foreign_net_5d_amt=_nan_to_none(r.foreign_net_5d_amt),
                        institution_net_20d_pct_mcap=_nan_to_none(
                            r.institution_net_20d_pct_mcap
                        ),
                        retail_streak_days=int(r.retail_streak_days),
                        foreign_flow_z_60d=_nan_to_none(r.foreign_flow_z_60d),
                        price_return_5d=_nan_to_none(r.price_return_5d),
                        volatility_20d=_nan_to_none(r.volatility_20d),
                    )
                )
                written += 1
            logger.info("[%s] feature rows: %d", ticker, len(feats))
    logger.info("Feature generation complete: %d rows", written)
    return written


def _nan_to_none(value):
    """Convert pandas/NumPy NaN to None for clean SQL NULLs."""
    if value is None or pd.isna(value):
        return None
    return float(value)
