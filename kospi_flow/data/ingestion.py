"""Ingestion service.

Pulls rows from a :class:`MarketDataProvider` and writes them into the core
tables. Ingestion is idempotent (re-running the same range upserts on primary
key rather than duplicating) and never silently drops rows — counts are logged
and returned (context doc, section 19.1).

Raw provider output is also persisted to ``data/raw`` as Parquet before
transformation, per the "store raw before transforming" rule.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import delete, select

from kospi_flow.core.config import Settings, get_settings
from kospi_flow.core.db import Database, get_database
from kospi_flow.core.enums import FreshnessState
from kospi_flow.core.logging import get_logger
from kospi_flow.core.models import (
    DimStock,
    FactForeignHoldingDaily,
    FactIndexDaily,
    FactInvestorFlowDaily,
    FactPriceDaily,
    IngestionCheckpoint,
)

#: Index pseudo-ticker used in the backfill checkpoint table.
_INDEX_KEY = "__index__"
from kospi_flow.data.providers import MarketDataProvider, get_provider

logger = get_logger(__name__)


@dataclass
class IngestionResult:
    """Counts produced by an ingestion run."""

    stocks: int = 0
    price_rows: int = 0
    flow_rows: int = 0
    foreign_rows: int = 0
    index_rows: int = 0
    skipped_foreign: bool = False
    tickers: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"stocks={self.stocks} price_rows={self.price_rows} "
            f"flow_rows={self.flow_rows} foreign_rows={self.foreign_rows} "
            f"index_rows={self.index_rows} skipped_foreign={self.skipped_foreign}"
        )


class Ingestor:
    """Coordinates pulling from a provider and writing to the database."""

    def __init__(
        self,
        provider: MarketDataProvider,
        database: Database,
        settings: Settings | None = None,
        freshness_state: FreshnessState = FreshnessState.FINAL_EOD,
    ) -> None:
        self.provider = provider
        self.db = database
        self.settings = settings or get_settings()
        self.freshness_state = freshness_state

    # -- raw storage --------------------------------------------------------
    def _write_raw(self, rows: list, kind: str, ticker: str) -> None:
        """Persist immutable raw rows as Parquet before transformation."""
        if not rows:
            return
        self.settings.ensure_storage_dirs()
        out_dir = self.settings.raw_data_path / kind
        out_dir.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame([asdict(r) for r in rows])
        path = out_dir / f"{kind}_{ticker}.parquet"
        try:
            df.to_parquet(path, index=False)
        except Exception as exc:  # pragma: no cover - depends on parquet engine
            # Parquet engine unavailable: fall back to CSV so raw data is still
            # persisted before transformation (context doc §19.1).
            csv_path = out_dir / f"{kind}_{ticker}.csv"
            df.to_csv(csv_path, index=False)
            logger.warning(
                "Parquet write failed (%s); wrote raw CSV instead: %s",
                exc,
                csv_path,
            )

    # -- universe -----------------------------------------------------------
    def ingest_universe(self, market: str | None = None) -> int:
        market = market or self.settings.market
        metas = self.provider.get_ticker_universe(market)
        with self.db.session() as s:
            for m in metas:
                s.merge(
                    DimStock(
                        ticker=m.ticker,
                        isin=m.isin,
                        name_kr=m.name_kr,
                        name_en=m.name_en,
                        market=m.market,
                        sector=m.sector,
                        listing_date=m.listing_date,
                        delisting_date=m.delisting_date,
                        is_preferred=m.is_preferred,
                        is_active=m.is_active,
                    )
                )
        logger.info("Ingested %d stocks into dim_stock", len(metas))
        return len(metas)

    # -- per-ticker facts ---------------------------------------------------
    def ingest_prices(self, ticker: str, start: date, end: date) -> int:
        rows = self.provider.get_price_daily(ticker, start, end)
        self._write_raw(rows, "price", ticker)
        with self.db.session() as s:
            for r in rows:
                s.merge(
                    FactPriceDaily(
                        date=r.date,
                        ticker=r.ticker,
                        open=r.open,
                        high=r.high,
                        low=r.low,
                        close=r.close,
                        adj_close=r.adj_close,
                        volume=r.volume,
                        trading_value=r.trading_value,
                        market_cap=r.market_cap,
                        shares_outstanding=r.shares_outstanding,
                        return_1d=r.return_1d,
                        source=self.provider.name,
                        freshness_state=self.freshness_state.value,
                    )
                )
        logger.info("[%s] price rows: %d", ticker, len(rows))
        return len(rows)

    def ingest_flows(self, ticker: str, start: date, end: date) -> int:
        rows = self.provider.get_investor_flow_daily(ticker, start, end)
        self._write_raw(rows, "investor_flow", ticker)
        with self.db.session() as s:
            for r in rows:
                s.merge(
                    FactInvestorFlowDaily(
                        date=r.date,
                        ticker=r.ticker,
                        investor_group=r.investor_group,
                        buy_volume=r.buy_volume,
                        sell_volume=r.sell_volume,
                        net_buy_volume=r.net_buy_volume,
                        buy_amount=r.buy_amount,
                        sell_amount=r.sell_amount,
                        net_buy_amount=r.net_buy_amount,
                        source=self.provider.name,
                        freshness_state=self.freshness_state.value,
                    )
                )
        logger.info("[%s] investor-flow rows: %d", ticker, len(rows))
        return len(rows)

    def ingest_foreign_holdings(self, ticker: str, start: date, end: date) -> int:
        rows = self.provider.get_foreign_holding_daily(ticker, start, end)
        self._write_raw(rows, "foreign_holding", ticker)
        with self.db.session() as s:
            for r in rows:
                s.merge(
                    FactForeignHoldingDaily(
                        date=r.date,
                        ticker=r.ticker,
                        foreign_held_shares=r.foreign_held_shares,
                        foreign_ownership_pct=r.foreign_ownership_pct,
                        foreign_limit_shares=r.foreign_limit_shares,
                        foreign_limit_exhaustion_pct=r.foreign_limit_exhaustion_pct,
                        source=self.provider.name,
                        freshness_state=self.freshness_state.value,
                    )
                )
        logger.info("[%s] foreign-holding rows: %d", ticker, len(rows))
        return len(rows)

    def ingest_index(self, index_code: str, start: date, end: date) -> int:
        rows = self.provider.get_index_ohlcv(index_code, start, end)
        self._write_raw(rows, "index", index_code)
        with self.db.session() as s:
            for r in rows:
                s.merge(
                    FactIndexDaily(
                        date=r.date,
                        index_code=r.index_code,
                        name=r.name,
                        open=r.open,
                        high=r.high,
                        low=r.low,
                        close=r.close,
                        return_1d=r.return_1d,
                        source=self.provider.name,
                        freshness_state=self.freshness_state.value,
                    )
                )
        logger.info("[index %s] rows: %d", index_code, len(rows))
        return len(rows)

    # -- orchestration ------------------------------------------------------
    def run(
        self,
        start: date,
        end: date,
        tickers: list[str] | None = None,
        market: str | None = None,
        include_foreign: bool = True,
        include_index: bool = True,
        index_codes: list[str] | None = None,
    ) -> IngestionResult:
        """Ingest universe + per-ticker facts + benchmark index for the range."""
        result = IngestionResult()
        result.stocks = self.ingest_universe(market)

        if tickers is None:
            metas = self.provider.get_ticker_universe(market or self.settings.market)
            tickers = [m.ticker for m in metas]
        result.tickers = list(tickers)

        for ticker in tickers:
            result.price_rows += self.ingest_prices(ticker, start, end)
            result.flow_rows += self.ingest_flows(ticker, start, end)
            if include_foreign and self.provider.supports_foreign_holdings:
                result.foreign_rows += self.ingest_foreign_holdings(
                    ticker, start, end
                )
            else:
                result.skipped_foreign = True

        if include_index and self.provider.supports_index:
            codes = index_codes or [self.settings.benchmark_index_code]
            for code in codes:
                result.index_rows += self.ingest_index(code, start, end)

        logger.info("Ingestion complete: %s", result.summary())
        return result

    # -- resumable backfill -------------------------------------------------
    def _scope_key(self, start: date, end: date) -> str:
        return f"{start.isoformat()}:{end.isoformat()}"

    def _completed(self, scope: str) -> set[str]:
        """Tickers already finished for this scope (status done/skipped)."""
        with self.db.session() as s:
            rows = s.execute(
                select(IngestionCheckpoint.ticker)
                .where(IngestionCheckpoint.scope_key == scope)
                .where(IngestionCheckpoint.status.in_(["done", "skipped"]))
            ).all()
        return {t for (t,) in rows}

    def _mark(self, scope: str, ticker: str, rows: int, max_empty: int) -> None:
        """Record progress: done if rows>0, else empty (retry) / skipped."""
        with self.db.session() as s:
            cp = s.get(IngestionCheckpoint, (scope, ticker))
            prev_attempts = cp.attempts if cp else 0
            if rows and rows > 0:
                status, attempts = "done", prev_attempts
            else:
                attempts = prev_attempts + 1
                status = "skipped" if attempts >= max_empty else "empty"
            s.merge(
                IngestionCheckpoint(
                    scope_key=scope,
                    ticker=ticker,
                    status=status,
                    rows=rows,
                    attempts=attempts,
                )
            )

    def backfill(
        self,
        start: date,
        end: date,
        tickers: list[str] | None = None,
        market: str | None = None,
        include_foreign: bool = True,
        include_index: bool = True,
        restart: bool = False,
        max_empty_attempts: int = 5,
    ) -> IngestionResult:
        """Resumable backfill of ``[start, end]``, one ticker at a time.

        Progress is checkpointed per ticker keyed by the ``(start, end)`` scope,
        so **re-running the exact same command picks up where it left off** —
        already-loaded tickers are skipped and only the remainder are fetched.
        This is the intended workflow when a data-source session (e.g. a pykrx
        KRX login) times out mid-run: re-authenticate, re-run the same command,
        and it continues. Use ``restart=True`` to clear the scope's checkpoints
        and start over.

        A ticker is marked ``done`` once it returns data; a ticker that returns
        nothing (token expired, or genuinely no data) is retried on later runs
        until ``max_empty_attempts``, after which it is ``skipped``.

        NOTE: keep ``start``/``end`` fixed across re-runs (use literal dates, not
        "today") so every run shares the same scope and resumes correctly.
        """
        scope = self._scope_key(start, end)
        if restart:
            with self.db.session() as s:
                s.execute(
                    delete(IngestionCheckpoint).where(
                        IngestionCheckpoint.scope_key == scope
                    )
                )
            logger.info("Cleared backfill checkpoints for scope %s", scope)

        total = IngestionResult()
        total.stocks = self.ingest_universe(market)
        if tickers is None:
            metas = self.provider.get_ticker_universe(market or self.settings.market)
            tickers = [m.ticker for m in metas]
        total.tickers = list(tickers)

        completed = self._completed(scope)
        pending = [t for t in tickers if t not in completed]
        logger.info(
            "Backfill scope %s: %d/%d ticker(s) already done, %d pending.",
            scope,
            len(completed),
            len(tickers),
            len(pending),
        )

        for i, ticker in enumerate(pending, start=1):
            p = self.ingest_prices(ticker, start, end)
            f = self.ingest_flows(ticker, start, end)
            fh = 0
            if include_foreign and self.provider.supports_foreign_holdings:
                fh = self.ingest_foreign_holdings(ticker, start, end)
            else:
                total.skipped_foreign = True
            total.price_rows += p
            total.flow_rows += f
            total.foreign_rows += fh
            # Price presence is the completion signal (it's fetched first and is
            # the most universally available series).
            self._mark(scope, ticker, p, max_empty_attempts)
            if i % 25 == 0 or i == len(pending):
                logger.info("  ...processed %d/%d pending tickers", i, len(pending))

        if include_index and self.provider.supports_index and _INDEX_KEY not in completed:
            ir = 0
            for code in [self.settings.benchmark_index_code]:
                ir += self.ingest_index(code, start, end)
            total.index_rows += ir
            self._mark(scope, _INDEX_KEY, ir, max_empty_attempts)

        still_pending = len(
            [t for t in tickers if t not in self._completed(scope)]
        )
        if still_pending:
            logger.warning(
                "Backfill pass done: %s | %d ticker(s) still pending — re-run the "
                "same command (after re-login) to continue.",
                total.summary(),
                still_pending,
            )
        else:
            logger.info("Backfill COMPLETE for scope %s: %s", scope, total.summary())
        return total


def chunked_date_ranges(
    start: date, end: date, chunk_days: int
) -> list[tuple[date, date]]:
    """Split ``[start, end]`` into inclusive sub-ranges of <= ``chunk_days``."""
    if chunk_days < 1:
        raise ValueError("chunk_days must be >= 1")
    out: list[tuple[date, date]] = []
    cur = start
    while cur <= end:
        c_end = min(cur + timedelta(days=chunk_days - 1), end)
        out.append((cur, c_end))
        cur = c_end + timedelta(days=1)
    return out


def build_ingestor(
    settings: Settings | None = None,
    database: Database | None = None,
    freshness_state: FreshnessState = FreshnessState.FINAL_EOD,
) -> Ingestor:
    """Construct an :class:`Ingestor` from settings (provider chosen by config)."""
    settings = settings or get_settings()
    database = database or get_database(settings)
    provider = get_provider(settings.data_source)
    return Ingestor(provider, database, settings, freshness_state)
