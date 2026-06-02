"""SQLAlchemy ORM models — the single source of truth for the schema.

These mirror the logical tables in the project context document (section 7).
The Alembic baseline migration creates these same tables, and
``tests/test_models.py`` asserts the two stay in sync.

Design note: monetary/volume measures use ``Float`` (DOUBLE PRECISION) rather
than fixed-precision ``Numeric``. KRW amounts fit exactly in float64 integer
range (< 2**53), and this avoids ``Decimal``/float friction in feature math for
the MVP. A production PostgreSQL deployment may switch large KRW columns to
``NUMERIC`` — tracked as known technical debt.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all tables."""


class TimestampMixin:
    """Audit columns present on every table."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class DimStock(TimestampMixin, Base):
    """Stock metadata (context doc 7.1)."""

    __tablename__ = "dim_stock"

    ticker: Mapped[str] = mapped_column(String(6), primary_key=True)
    isin: Mapped[str | None] = mapped_column(String(12), nullable=True)
    name_kr: Mapped[str | None] = mapped_column(String, nullable=True)
    name_en: Mapped[str | None] = mapped_column(String, nullable=True)
    market: Mapped[str] = mapped_column(String, default="KOSPI", nullable=False)
    sector: Mapped[str | None] = mapped_column(String, nullable=True)
    listing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    delisting_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_preferred: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class FactPriceDaily(TimestampMixin, Base):
    """Daily price, volume, and market-cap data (context doc 7.2)."""

    __tablename__ = "fact_price_daily"

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    ticker: Mapped[str] = mapped_column(
        String(6), ForeignKey("dim_stock.ticker"), primary_key=True
    )
    open: Mapped[float | None] = mapped_column(Float, nullable=True)
    high: Mapped[float | None] = mapped_column(Float, nullable=True)
    low: Mapped[float | None] = mapped_column(Float, nullable=True)
    close: Mapped[float | None] = mapped_column(Float, nullable=True)
    adj_close: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    trading_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    market_cap: Mapped[float | None] = mapped_column(Float, nullable=True)
    shares_outstanding: Mapped[float | None] = mapped_column(Float, nullable=True)
    #: Simple (not log) daily return; documented here to avoid ambiguity.
    return_1d: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str | None] = mapped_column(String, nullable=True)
    freshness_state: Mapped[str | None] = mapped_column(String, nullable=True)


class FactInvestorFlowDaily(TimestampMixin, Base):
    """Investor buy/sell/net-flow by stock/date/group (context doc 7.3)."""

    __tablename__ = "fact_investor_flow_daily"

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    ticker: Mapped[str] = mapped_column(
        String(6), ForeignKey("dim_stock.ticker"), primary_key=True
    )
    investor_group: Mapped[str] = mapped_column(String, primary_key=True)
    buy_volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    sell_volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_buy_volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    buy_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    sell_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_buy_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str | None] = mapped_column(String, nullable=True)
    freshness_state: Mapped[str | None] = mapped_column(String, nullable=True)


class FactForeignHoldingDaily(TimestampMixin, Base):
    """Actual foreign ownership data (context doc 7.4)."""

    __tablename__ = "fact_foreign_holding_daily"

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    ticker: Mapped[str] = mapped_column(
        String(6), ForeignKey("dim_stock.ticker"), primary_key=True
    )
    foreign_held_shares: Mapped[float | None] = mapped_column(Float, nullable=True)
    foreign_ownership_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    foreign_limit_shares: Mapped[float | None] = mapped_column(Float, nullable=True)
    foreign_limit_exhaustion_pct: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    source: Mapped[str | None] = mapped_column(String, nullable=True)
    freshness_state: Mapped[str | None] = mapped_column(String, nullable=True)


class FactFeaturesDaily(TimestampMixin, Base):
    """Precomputed features for screeners/analytics/ML (context doc 7.5).

    ``feature_version`` is part of the key so multiple feature-set versions can
    coexist for the same (date, ticker) during model iteration.
    """

    __tablename__ = "fact_features_daily"

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    ticker: Mapped[str] = mapped_column(
        String(6), ForeignKey("dim_stock.ticker"), primary_key=True
    )
    feature_version: Mapped[str] = mapped_column(
        String, primary_key=True, default="v0"
    )
    foreign_net_5d_amt: Mapped[float | None] = mapped_column(Float, nullable=True)
    institution_net_20d_pct_mcap: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    retail_streak_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    foreign_flow_z_60d: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_return_5d: Mapped[float | None] = mapped_column(Float, nullable=True)
    volatility_20d: Mapped[float | None] = mapped_column(Float, nullable=True)


class FactMlPredictionDaily(TimestampMixin, Base):
    """Model predictions (context doc 7.6). Populated from Phase 4 onward."""

    __tablename__ = "fact_ml_prediction_daily"

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    ticker: Mapped[str] = mapped_column(
        String(6), ForeignKey("dim_stock.ticker"), primary_key=True
    )
    horizon_days: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_name: Mapped[str] = mapped_column(String, primary_key=True)
    predicted_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    predicted_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    predicted_return_p10: Mapped[float | None] = mapped_column(Float, nullable=True)
    predicted_return_p50: Mapped[float | None] = mapped_column(Float, nullable=True)
    predicted_return_p90: Mapped[float | None] = mapped_column(Float, nullable=True)
    prob_outperform_kospi: Mapped[float | None] = mapped_column(Float, nullable=True)
    model_version: Mapped[str | None] = mapped_column(String, nullable=True)
    feature_version: Mapped[str | None] = mapped_column(String, nullable=True)


class FactIndexDaily(TimestampMixin, Base):
    """Daily market-index OHLC (e.g. KOSPI index code ``1001``).

    Used as the benchmark for outperformance labels and market views. When
    present it replaces the cap-weighted proxy computed from the stock universe.
    """

    __tablename__ = "fact_index_daily"

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    index_code: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    open: Mapped[float | None] = mapped_column(Float, nullable=True)
    high: Mapped[float | None] = mapped_column(Float, nullable=True)
    low: Mapped[float | None] = mapped_column(Float, nullable=True)
    close: Mapped[float | None] = mapped_column(Float, nullable=True)
    return_1d: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str | None] = mapped_column(String, nullable=True)
    freshness_state: Mapped[str | None] = mapped_column(String, nullable=True)


class MlModelRegistry(TimestampMixin, Base):
    """Registry of trained models + their out-of-sample metrics (Phase 5).

    One row per (model_name, model_version). ``is_active`` marks the version
    that inference should use for a given model_name.
    """

    __tablename__ = "ml_model_registry"

    model_name: Mapped[str] = mapped_column(String, primary_key=True)
    model_version: Mapped[str] = mapped_column(String, primary_key=True)
    horizon_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feature_version: Mapped[str | None] = mapped_column(String, nullable=True)
    backend: Mapped[str | None] = mapped_column(String, nullable=True)
    trained_at: Mapped[str | None] = mapped_column(String, nullable=True)
    n_samples: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mean_ic: Mapped[float | None] = mapped_column(Float, nullable=True)
    icir: Mapped[float | None] = mapped_column(Float, nullable=True)
    rmse: Mapped[float | None] = mapped_column(Float, nullable=True)
    mae: Mapped[float | None] = mapped_column(Float, nullable=True)
    auc: Mapped[float | None] = mapped_column(Float, nullable=True)
    metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    artifact_path: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class FactModelDriftDaily(TimestampMixin, Base):
    """Per-run feature-drift summary for a model (Phase 5 monitoring).

    PSI compares the live feature distribution against the model's training
    baseline. ``status`` is ok/warning/alert from PSI thresholds.
    """

    __tablename__ = "fact_model_drift_daily"

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    model_name: Mapped[str] = mapped_column(String, primary_key=True)
    model_version: Mapped[str | None] = mapped_column(String, nullable=True)
    max_psi: Mapped[float | None] = mapped_column(Float, nullable=True)
    mean_psi: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    n_rows: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Watchlist(TimestampMixin, Base):
    """A named user watchlist (Phase 5). No auth in the MVP — name is the key."""

    __tablename__ = "watchlist"

    name: Mapped[str] = mapped_column(String, primary_key=True)
    description: Mapped[str | None] = mapped_column(String, nullable=True)


class WatchlistItem(TimestampMixin, Base):
    """Membership of a ticker in a watchlist (Phase 5)."""

    __tablename__ = "watchlist_item"

    watchlist_name: Mapped[str] = mapped_column(
        String, ForeignKey("watchlist.name"), primary_key=True
    )
    ticker: Mapped[str] = mapped_column(
        String(6), ForeignKey("dim_stock.ticker"), primary_key=True
    )


class IngestionCheckpoint(TimestampMixin, Base):
    """Per-ticker backfill progress so a re-run resumes where it left off.

    A row is recorded after a ticker is ingested for a given backfill scope
    (``scope_key`` = ``"<start>:<end>"``). ``status`` is ``done`` once real data
    was returned, ``empty`` while a ticker keeps returning no data (e.g. a token
    expired mid-run — it will be retried next run), or ``skipped`` after too many
    empty attempts (likely genuinely dataless). Resumable backfill skips
    ``done``/``skipped`` tickers. ``__index__`` is used as the index pseudo-ticker.
    """

    __tablename__ = "ingestion_checkpoint"

    scope_key: Mapped[str] = mapped_column(String, primary_key=True)
    ticker: Mapped[str] = mapped_column(String, primary_key=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    rows: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


#: All ORM tables, handy for tests and tooling.
ALL_TABLES = (
    DimStock,
    FactPriceDaily,
    FactInvestorFlowDaily,
    FactForeignHoldingDaily,
    FactFeaturesDaily,
    FactMlPredictionDaily,
    FactIndexDaily,
    MlModelRegistry,
    FactModelDriftDaily,
    Watchlist,
    WatchlistItem,
    IngestionCheckpoint,
)
