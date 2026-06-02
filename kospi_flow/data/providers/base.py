"""Provider abstraction.

Every data source — the offline ``sample`` generator, the ``pykrx`` prototype,
or a future licensed vendor — implements :class:`MarketDataProvider`. Ingestion
code depends only on this interface, so the source can be swapped via the
``KOSPI_DATA_SOURCE`` setting without touching the pipeline.

Provider methods return plain dataclasses (not ORM objects) so providers stay
decoupled from the database layer.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class StockMeta:
    """One row destined for ``dim_stock``."""

    ticker: str
    name_kr: str | None = None
    name_en: str | None = None
    market: str = "KOSPI"
    sector: str | None = None
    isin: str | None = None
    listing_date: date | None = None
    delisting_date: date | None = None
    is_preferred: bool = False
    is_active: bool = True


@dataclass(frozen=True)
class PriceRow:
    """One row destined for ``fact_price_daily``."""

    date: date
    ticker: str
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    adj_close: float | None = None
    volume: float | None = None
    trading_value: float | None = None
    market_cap: float | None = None
    shares_outstanding: float | None = None
    return_1d: float | None = None


@dataclass(frozen=True)
class InvestorFlowRow:
    """One row destined for ``fact_investor_flow_daily``.

    ``investor_group`` should be one of :class:`kospi_flow.core.enums.InvestorGroup`
    values.
    """

    date: date
    ticker: str
    investor_group: str
    buy_volume: float | None = None
    sell_volume: float | None = None
    net_buy_volume: float | None = None
    buy_amount: float | None = None
    sell_amount: float | None = None
    net_buy_amount: float | None = None


@dataclass(frozen=True)
class ForeignHoldingRow:
    """One row destined for ``fact_foreign_holding_daily``."""

    date: date
    ticker: str
    foreign_held_shares: float | None = None
    foreign_ownership_pct: float | None = None
    foreign_limit_shares: float | None = None
    foreign_limit_exhaustion_pct: float | None = None


@dataclass(frozen=True)
class IndexRow:
    """One row destined for ``fact_index_daily`` (e.g. the KOSPI index)."""

    date: date
    index_code: str
    name: str | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    return_1d: float | None = None


class MarketDataProvider(ABC):
    """Interface every data source must implement.

    Implementations must:
      * be read-only with respect to the source,
      * return rows for the inclusive ``[start, end]`` date range,
      * raise rather than silently returning partial data on hard errors.

    A provider that genuinely cannot serve a data need (e.g. foreign holdings)
    may return an empty list, but should document why.
    """

    #: Stable identifier written to the ``source`` column of ingested rows.
    name: str = "base"

    #: Whether this provider can supply actual foreign-holding data.
    supports_foreign_holdings: bool = True

    #: Whether this provider can supply market-index series.
    supports_index: bool = False

    @abstractmethod
    def get_ticker_universe(self, market: str = "KOSPI") -> list[StockMeta]:
        """Return the stock universe for ``market``."""

    @abstractmethod
    def get_price_daily(
        self, ticker: str, start: date, end: date
    ) -> list[PriceRow]:
        """Return daily OHLCV/market-cap rows for ``ticker``."""

    @abstractmethod
    def get_investor_flow_daily(
        self, ticker: str, start: date, end: date
    ) -> list[InvestorFlowRow]:
        """Return daily investor-flow rows for ``ticker`` (all groups)."""

    @abstractmethod
    def get_foreign_holding_daily(
        self, ticker: str, start: date, end: date
    ) -> list[ForeignHoldingRow]:
        """Return daily foreign-holding rows for ``ticker``.

        Return ``[]`` if the provider cannot supply this data.
        """

    def get_index_ohlcv(
        self, index_code: str, start: date, end: date
    ) -> list[IndexRow]:
        """Return daily index OHLC rows (e.g. KOSPI ``1001``).

        Not abstract: providers that cannot supply an index return ``[]`` (the
        default), and the benchmark falls back to the cap-weighted proxy.
        """
        return []
