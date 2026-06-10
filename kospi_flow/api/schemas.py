"""Pydantic request models for the API."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

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


class ExternalPredictionRow(BaseModel):
    """One prediction from an external model (docs/EXTERNAL_MODELS.md).

    Returns are log returns over ``horizon_days`` trading days, matching the
    internal models. Only ``predicted_return`` is required; the band/probability
    fields enrich the UI when the external model can provide them.
    """

    date: date
    ticker: str = Field(min_length=6, max_length=6)
    horizon_days: int = Field(ge=1, le=60)
    predicted_return: float
    predicted_price: float | None = None
    predicted_return_p10: float | None = None
    predicted_return_p50: float | None = None
    predicted_return_p90: float | None = None
    prob_outperform_kospi: float | None = Field(default=None, ge=0.0, le=1.0)


class ExternalPredictionsPayload(BaseModel):
    """Batch upsert of external-model predictions."""

    # Allow the ``model_version`` field name (pydantic reserves ``model_``).
    model_config = ConfigDict(protected_namespaces=())

    model_version: str = Field(default="v1", min_length=1, max_length=64)
    feature_version: str | None = None
    predictions: list[ExternalPredictionRow] = Field(min_length=1, max_length=20000)
