"""Offline deterministic sample provider.

Generates realistic-shaped synthetic data for a small fixed KOSPI-like
universe. It requires no network access or credentials, so the full ingestion
pipeline, validation, and tests run anywhere. Output is fully deterministic:
the same ``(ticker, date)`` always yields the same numbers, which keeps tests
stable and ingestion idempotent.

The data is synthetic and clearly labelled (``source = "sample"``). It must
never be presented to users as real market data.
"""

from __future__ import annotations

import hashlib
from datetime import date

import numpy as np
import pandas as pd

from kospi_flow.core.enums import MVP_INVESTOR_GROUPS, InvestorGroup
from kospi_flow.data.providers.base import (
    ForeignHoldingRow,
    IndexRow,
    InvestorFlowRow,
    MarketDataProvider,
    PriceRow,
    StockMeta,
)

# Synthetic KOSPI-like index: code -> (display name, base level).
_INDEX_META: dict[str, tuple[str, float]] = {
    "1001": ("코스피", 2500.0),
}

# A small, fixed universe loosely modelled on well-known KOSPI names so the
# sample data is recognisable. These are synthetic, not real market figures.
_UNIVERSE: list[dict] = [
    {"ticker": "005930", "name_kr": "삼성전자", "name_en": "Samsung Electronics",
     "sector": "IT", "base_price": 70000, "shares": 5_969_782_550},
    {"ticker": "000660", "name_kr": "SK하이닉스", "name_en": "SK hynix",
     "sector": "IT", "base_price": 130000, "shares": 728_002_365},
    {"ticker": "373220", "name_kr": "LG에너지솔루션", "name_en": "LG Energy Solution",
     "sector": "Materials", "base_price": 400000, "shares": 234_000_000},
    {"ticker": "207940", "name_kr": "삼성바이오로직스", "name_en": "Samsung Biologics",
     "sector": "Healthcare", "base_price": 780000, "shares": 71_174_000},
    {"ticker": "005380", "name_kr": "현대차", "name_en": "Hyundai Motor",
     "sector": "Consumer Discretionary", "base_price": 200000, "shares": 209_416_191},
    {"ticker": "005935", "name_kr": "삼성전자우", "name_en": "Samsung Electronics (pref)",
     "sector": "IT", "base_price": 58000, "shares": 822_886_700,
     "is_preferred": True},
]


def _seed(*parts: str) -> int:
    """Stable 32-bit seed derived from string parts (no global RNG / clock)."""
    digest = hashlib.sha256("|".join(parts).encode()).digest()
    return int.from_bytes(digest[:4], "big")


class SampleProvider(MarketDataProvider):
    """Deterministic synthetic data source for MVP/testing."""

    name = "sample"
    supports_foreign_holdings = True
    supports_index = True

    def __init__(self, market: str = "KOSPI") -> None:
        self.market = market
        self._meta = {row["ticker"]: row for row in _UNIVERSE}

    # -- universe -----------------------------------------------------------
    def get_ticker_universe(self, market: str = "KOSPI") -> list[StockMeta]:
        return [
            StockMeta(
                ticker=row["ticker"],
                name_kr=row["name_kr"],
                name_en=row["name_en"],
                market=market,
                sector=row["sector"],
                is_preferred=row.get("is_preferred", False),
                is_active=True,
            )
            for row in _UNIVERSE
        ]

    # -- helpers ------------------------------------------------------------
    def _trading_days(self, start: date, end: date) -> list[date]:
        """Business days (Mon–Fri) in range. Holidays are not modelled."""
        rng = pd.bdate_range(start=start, end=end)
        return [d.date() for d in rng]

    def _price_frame(self, ticker: str, days: list[date]) -> pd.DataFrame:
        """Deterministic price path + derived columns for ``ticker``."""
        meta = self._meta.get(ticker, {"base_price": 50000, "shares": 100_000_000})
        n = len(days)
        rng = np.random.RandomState(_seed("price", ticker))
        # Geometric random walk with mild drift.
        daily_ret = rng.normal(loc=0.0003, scale=0.018, size=n)
        if n:
            daily_ret[0] = 0.0
        close = float(meta["base_price"]) * np.exp(np.cumsum(daily_ret))
        intraday = np.abs(rng.normal(0, 0.01, size=n))
        open_ = close * (1 - daily_ret * 0.5)
        high = np.maximum(open_, close) * (1 + intraday)
        low = np.minimum(open_, close) * (1 - intraday)
        volume = rng.randint(1_000_000, 20_000_000, size=n).astype(float)
        shares = float(meta["shares"])
        df = pd.DataFrame(
            {
                "date": days,
                "open": np.round(open_, 0),
                "high": np.round(high, 0),
                "low": np.round(low, 0),
                "close": np.round(close, 0),
                "volume": volume,
            }
        )
        # No corporate actions in sample data -> adj_close == close.
        df["adj_close"] = df["close"]
        df["trading_value"] = (df["close"] * df["volume"]).round(0)
        df["shares_outstanding"] = shares
        df["market_cap"] = (df["close"] * shares).round(0)
        df["return_1d"] = df["close"].pct_change()
        return df

    # -- prices -------------------------------------------------------------
    def get_price_daily(
        self, ticker: str, start: date, end: date
    ) -> list[PriceRow]:
        days = self._trading_days(start, end)
        df = self._price_frame(ticker, days)
        rows: list[PriceRow] = []
        for r in df.itertuples(index=False):
            rows.append(
                PriceRow(
                    date=r.date,
                    ticker=ticker,
                    open=float(r.open),
                    high=float(r.high),
                    low=float(r.low),
                    close=float(r.close),
                    adj_close=float(r.adj_close),
                    volume=float(r.volume),
                    trading_value=float(r.trading_value),
                    market_cap=float(r.market_cap),
                    shares_outstanding=float(r.shares_outstanding),
                    return_1d=None if pd.isna(r.return_1d) else float(r.return_1d),
                )
            )
        return rows

    # -- investor flow ------------------------------------------------------
    def get_investor_flow_daily(
        self, ticker: str, start: date, end: date
    ) -> list[InvestorFlowRow]:
        days = self._trading_days(start, end)
        price_df = self._price_frame(ticker, days).set_index("date")
        rows: list[InvestorFlowRow] = []
        # Generate net amounts per group such that the three MVP groups roughly
        # net out (one buys what the others sell), which mirrors reality where
        # daily net flows across all participants sum to ~0.
        rng = np.random.RandomState(_seed("flow", ticker))
        n = len(days)
        foreign_net_amt = rng.normal(0, 5e9, size=n)
        inst_net_amt = rng.normal(0, 4e9, size=n)
        retail_net_amt = -(foreign_net_amt + inst_net_amt)
        group_amts = {
            InvestorGroup.FOREIGN: foreign_net_amt,
            InvestorGroup.INSTITUTION: inst_net_amt,
            InvestorGroup.RETAIL: retail_net_amt,
        }
        for i, d in enumerate(days):
            close = float(price_df.loc[d, "close"])
            total_val = float(price_df.loc[d, "trading_value"])
            for group in MVP_INVESTOR_GROUPS:
                net_amt = float(group_amts[group][i])
                net_vol = net_amt / close if close else 0.0
                # Split net into buy/sell using a per-day gross turnover share.
                gross = abs(net_amt) + total_val * 0.05
                buy_amt = (gross + net_amt) / 2
                sell_amt = (gross - net_amt) / 2
                rows.append(
                    InvestorFlowRow(
                        date=d,
                        ticker=ticker,
                        investor_group=group.value,
                        buy_amount=round(buy_amt, 0),
                        sell_amount=round(sell_amt, 0),
                        net_buy_amount=round(net_amt, 0),
                        buy_volume=round(buy_amt / close, 0) if close else 0.0,
                        sell_volume=round(sell_amt / close, 0) if close else 0.0,
                        net_buy_volume=round(net_vol, 0),
                    )
                )
        return rows

    # -- foreign holdings ---------------------------------------------------
    def get_foreign_holding_daily(
        self, ticker: str, start: date, end: date
    ) -> list[ForeignHoldingRow]:
        days = self._trading_days(start, end)
        flows = self.get_investor_flow_daily(ticker, start, end)
        meta = self._meta.get(ticker, {"shares": 100_000_000})
        shares = float(meta["shares"])
        # Start from a deterministic baseline foreign holding, then accumulate
        # foreign net-buy volume to evolve the actual holding over time.
        rng = np.random.RandomState(_seed("foreign", ticker))
        base_pct = float(rng.uniform(0.15, 0.55))
        held = base_pct * shares
        foreign_net_by_date = {
            f.date: (f.net_buy_volume or 0.0)
            for f in flows
            if f.investor_group == InvestorGroup.FOREIGN.value
        }
        rows: list[ForeignHoldingRow] = []
        for d in days:
            held += foreign_net_by_date.get(d, 0.0)
            held = max(0.0, min(held, shares))
            rows.append(
                ForeignHoldingRow(
                    date=d,
                    ticker=ticker,
                    foreign_held_shares=round(held, 0),
                    foreign_ownership_pct=round(held / shares, 6) if shares else None,
                    foreign_limit_shares=shares,
                    foreign_limit_exhaustion_pct=(
                        round(held / shares, 6) if shares else None
                    ),
                )
            )
        return rows

    # -- index --------------------------------------------------------------
    def get_index_ohlcv(
        self, index_code: str, start: date, end: date
    ) -> list[IndexRow]:
        """Deterministic synthetic index series for ``index_code``.

        Generated independently of the stock universe so tests can confirm the
        benchmark uses the real index (not the cap-weighted proxy) when present.
        """
        name, base = _INDEX_META.get(index_code, (index_code, 2000.0))
        days = self._trading_days(start, end)
        n = len(days)
        if n == 0:
            return []
        rng = np.random.RandomState(_seed("index", index_code))
        daily_ret = rng.normal(loc=0.0002, scale=0.011, size=n)
        daily_ret[0] = 0.0
        close = base * np.exp(np.cumsum(daily_ret))
        intraday = np.abs(rng.normal(0, 0.004, size=n))
        open_ = close * (1 - daily_ret * 0.5)
        high = np.maximum(open_, close) * (1 + intraday)
        low = np.minimum(open_, close) * (1 - intraday)
        rows: list[IndexRow] = []
        prev = None
        for i, d in enumerate(days):
            c = float(round(close[i], 2))
            ret = None if prev is None else (c / prev - 1.0)
            prev = c
            rows.append(
                IndexRow(
                    date=d,
                    index_code=index_code,
                    name=name,
                    open=float(round(open_[i], 2)),
                    high=float(round(high[i], 2)),
                    low=float(round(low[i], 2)),
                    close=c,
                    return_1d=ret,
                )
            )
        return rows
