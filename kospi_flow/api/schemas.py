"""Pydantic request models for the API."""

from __future__ import annotations

from pydantic import BaseModel, Field

from kospi_flow.core.enums import InvestorGroup


class ScreenerRequest(BaseModel):
    """Investor-flow screener payload (context doc §8.3)."""

    market: str = "KOSPI"
    lookback_days: int = Field(default=5, ge=1, le=252)
    investor_groups: list[str] = Field(
        default_factory=lambda: [InvestorGroup.FOREIGN.value]
    )
    min_net_buy_amount: float | None = None
    min_net_buy_pct_mcap: float | None = None
    min_net_buy_volume_pct_shares: float | None = None
    min_consecutive_days: int | None = None
    min_avg_trading_value: float | None = None
    exclude_preferred: bool = True
    limit: int = Field(default=100, ge=1, le=1000)


class WatchlistCreate(BaseModel):
    """Create-watchlist payload."""

    name: str = Field(min_length=1, max_length=100)
    description: str | None = None


class WatchlistItemAdd(BaseModel):
    """Add-ticker-to-watchlist payload."""

    ticker: str = Field(min_length=6, max_length=6)
