"""Placeholder for a licensed/official production data provider.

This is the designated swap-in point for KRX/Koscom/broker/vendor data once a
source and license are finalised (context doc, sections 4 and 22). Implement
the four :class:`MarketDataProvider` methods here, register the provider in
``providers/__init__.py``, and set ``KOSPI_DATA_SOURCE=licensed``.
"""

from __future__ import annotations

from datetime import date

from kospi_flow.data.providers.base import (
    ForeignHoldingRow,
    IndexRow,
    InvestorFlowRow,
    MarketDataProvider,
    PriceRow,
    StockMeta,
)

_NOT_IMPLEMENTED = (
    "The licensed production provider is not implemented yet. A data source and "
    "license must be finalised first (see project context, open question #1). "
    "Use KOSPI_DATA_SOURCE=sample for offline data or =pykrx for a prototype."
)


class LicensedProvider(MarketDataProvider):
    """Not yet implemented — intentional placeholder."""

    name = "licensed"

    def get_ticker_universe(self, market: str = "KOSPI") -> list[StockMeta]:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def get_price_daily(
        self, ticker: str, start: date, end: date
    ) -> list[PriceRow]:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def get_investor_flow_daily(
        self, ticker: str, start: date, end: date
    ) -> list[InvestorFlowRow]:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def get_foreign_holding_daily(
        self, ticker: str, start: date, end: date
    ) -> list[ForeignHoldingRow]:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def get_index_ohlcv(
        self, index_code: str, start: date, end: date
    ) -> list[IndexRow]:
        raise NotImplementedError(_NOT_IMPLEMENTED)
