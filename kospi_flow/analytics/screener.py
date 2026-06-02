"""Investor-flow screener (context doc §8).

Pure-ish computation over the database: given a set of criteria, rank KOSPI
stocks by recent investor-position shifts. Kept independent of FastAPI so it is
testable directly and reusable by analytics.

All flow metrics are computed from ``net_buy_*`` (순매수) — never presented as
holdings. Foreign holdings are the only true-holding figures elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from kospi_flow.analytics.features import signed_streak
from kospi_flow.core.enums import InvestorGroup
from kospi_flow.core.models import DimStock, FactInvestorFlowDaily, FactPriceDaily


@dataclass
class ScreenerCriteria:
    """Screener filter payload (mirrors the example in context doc §8.3)."""

    market: str = "KOSPI"
    lookback_days: int = 5
    investor_groups: list[str] = field(
        default_factory=lambda: [InvestorGroup.FOREIGN.value]
    )
    min_net_buy_amount: float | None = None
    min_net_buy_pct_mcap: float | None = None
    min_net_buy_volume_pct_shares: float | None = None
    min_consecutive_days: int | None = None
    min_avg_trading_value: float | None = None
    exclude_preferred: bool = True
    limit: int = 100


@dataclass
class ScreenerRow:
    """One ranked screener result."""

    ticker: str
    name_kr: str | None
    sector: str | None
    as_of: date
    close: float | None
    market_cap: float | None
    net_buy_amount: float
    net_buy_volume: float
    net_buy_pct_mcap: float | None
    net_buy_volume_pct_shares: float | None
    avg_trading_value: float | None
    streak_days: int

    def as_dict(self) -> dict:
        d = self.__dict__.copy()
        d["as_of"] = self.as_of.isoformat()
        return d


def _load_flows(
    session: Session, groups: list[str]
) -> pd.DataFrame:
    rows = session.execute(
        select(
            FactInvestorFlowDaily.date,
            FactInvestorFlowDaily.ticker,
            FactInvestorFlowDaily.investor_group,
            FactInvestorFlowDaily.net_buy_amount,
            FactInvestorFlowDaily.net_buy_volume,
        ).where(FactInvestorFlowDaily.investor_group.in_(groups))
    ).all()
    return pd.DataFrame(
        rows,
        columns=[
            "date",
            "ticker",
            "investor_group",
            "net_buy_amount",
            "net_buy_volume",
        ],
    )


def run_screener(
    session: Session, criteria: ScreenerCriteria
) -> list[ScreenerRow]:
    """Execute a screener and return ranked rows (descending net-buy amount)."""
    groups = criteria.investor_groups or [InvestorGroup.FOREIGN.value]

    # Stock metadata for the requested market / preferred-share exclusion.
    meta_stmt = select(
        DimStock.ticker, DimStock.name_kr, DimStock.sector, DimStock.is_preferred
    ).where(DimStock.market == criteria.market)
    if criteria.exclude_preferred:
        meta_stmt = meta_stmt.where(DimStock.is_preferred.is_(False))
    meta = {
        t: {"name_kr": n, "sector": s}
        for (t, n, s, _pref) in session.execute(meta_stmt).all()
    }
    if not meta:
        return []

    price_rows = session.execute(
        select(
            FactPriceDaily.date,
            FactPriceDaily.ticker,
            FactPriceDaily.close,
            FactPriceDaily.market_cap,
            FactPriceDaily.shares_outstanding,
            FactPriceDaily.trading_value,
        ).where(FactPriceDaily.ticker.in_(list(meta)))
    ).all()
    price = pd.DataFrame(
        price_rows,
        columns=[
            "date",
            "ticker",
            "close",
            "market_cap",
            "shares_outstanding",
            "trading_value",
        ],
    )
    if price.empty:
        return []

    flows = _load_flows(session, groups)
    # Sum the selected groups into a combined daily net flow per (ticker, date).
    if flows.empty:
        flows = pd.DataFrame(
            columns=["date", "ticker", "net_buy_amount", "net_buy_volume"]
        )
    else:
        flows = (
            flows.groupby(["ticker", "date"], as_index=False)[
                ["net_buy_amount", "net_buy_volume"]
            ].sum()
        )

    results: list[ScreenerRow] = []
    lookback = max(1, criteria.lookback_days)

    for ticker, mrow in meta.items():
        tp = price[price["ticker"] == ticker].sort_values("date")
        if tp.empty:
            continue
        as_of = tp["date"].iloc[-1]
        window_dates = tp["date"].iloc[-lookback:].tolist()
        last = tp.iloc[-1]

        tf = flows[flows["ticker"] == ticker].sort_values("date")
        win = tf[tf["date"].isin(window_dates)]
        net_amt = float(win["net_buy_amount"].sum()) if not win.empty else 0.0
        net_vol = float(win["net_buy_volume"].sum()) if not win.empty else 0.0

        mcap = None if pd.isna(last["market_cap"]) else float(last["market_cap"])
        shares = (
            None
            if pd.isna(last["shares_outstanding"])
            else float(last["shares_outstanding"])
        )
        pct_mcap = net_amt / mcap if mcap else None
        pct_shares = net_vol / shares if shares else None

        win_price = tp[tp["date"].isin(window_dates)]
        avg_tv = (
            float(win_price["trading_value"].mean())
            if not win_price["trading_value"].isna().all()
            else None
        )

        # Streak over the full series of the combined net flow.
        if not tf.empty:
            streak = int(signed_streak(tf["net_buy_amount"].reset_index(drop=True)).iloc[-1])
        else:
            streak = 0

        results.append(
            ScreenerRow(
                ticker=ticker,
                name_kr=mrow["name_kr"],
                sector=mrow["sector"],
                as_of=as_of,
                close=None if pd.isna(last["close"]) else float(last["close"]),
                market_cap=mcap,
                net_buy_amount=net_amt,
                net_buy_volume=net_vol,
                net_buy_pct_mcap=pct_mcap,
                net_buy_volume_pct_shares=pct_shares,
                avg_trading_value=avg_tv,
                streak_days=streak,
            )
        )

    filtered = [r for r in results if _passes(r, criteria)]
    filtered.sort(key=lambda r: r.net_buy_amount, reverse=True)
    return filtered[: criteria.limit]


def _passes(r: ScreenerRow, c: ScreenerCriteria) -> bool:
    if c.min_net_buy_amount is not None and r.net_buy_amount < c.min_net_buy_amount:
        return False
    if c.min_net_buy_pct_mcap is not None and (
        r.net_buy_pct_mcap is None or r.net_buy_pct_mcap < c.min_net_buy_pct_mcap
    ):
        return False
    if c.min_net_buy_volume_pct_shares is not None and (
        r.net_buy_volume_pct_shares is None
        or r.net_buy_volume_pct_shares < c.min_net_buy_volume_pct_shares
    ):
        return False
    if c.min_consecutive_days is not None and r.streak_days < c.min_consecutive_days:
        return False
    if c.min_avg_trading_value is not None and (
        r.avg_trading_value is None or r.avg_trading_value < c.min_avg_trading_value
    ):
        return False
    return True
