"""Provider registry.

Resolve a provider by name (the ``KOSPI_DATA_SOURCE`` setting):

    >>> from kospi_flow.data.providers import get_provider
    >>> provider = get_provider("sample")
"""

from __future__ import annotations

from kospi_flow.data.providers.base import (
    ForeignHoldingRow,
    IndexRow,
    InvestorFlowRow,
    MarketDataProvider,
    PriceRow,
    StockMeta,
)
from kospi_flow.data.providers.licensed import LicensedProvider
from kospi_flow.data.providers.sample import SampleProvider

__all__ = [
    "MarketDataProvider",
    "StockMeta",
    "PriceRow",
    "InvestorFlowRow",
    "ForeignHoldingRow",
    "IndexRow",
    "get_provider",
    "available_providers",
]

# Lazy factories so optional dependencies (e.g. pykrx) are imported only when
# that provider is actually requested.
_REGISTRY: dict[str, callable] = {
    "sample": SampleProvider,
    "licensed": LicensedProvider,
}


def _make_pykrx() -> MarketDataProvider:
    from kospi_flow.data.providers.pykrx_provider import PykrxProvider

    return PykrxProvider()


_REGISTRY["pykrx"] = _make_pykrx


def available_providers() -> list[str]:
    """Names of registered providers."""
    return sorted(_REGISTRY)


def get_provider(name: str) -> MarketDataProvider:
    """Instantiate a provider by name. Raises ``ValueError`` if unknown."""
    try:
        factory = _REGISTRY[name]
    except KeyError:
        raise ValueError(
            f"Unknown data source '{name}'. Available: {available_providers()}"
        ) from None
    return factory()
