"""Schema assumptions: tables, primary keys, and migration/ORM parity."""

from __future__ import annotations

from sqlalchemy import create_engine, inspect

from kospi_flow.core.db import Database
from kospi_flow.core.models import Base

EXPECTED_TABLES = {
    "dim_stock",
    "fact_price_daily",
    "fact_investor_flow_daily",
    "fact_foreign_holding_daily",
    "fact_features_daily",
    "fact_ml_prediction_daily",
    "fact_index_daily",
    "ml_model_registry",
    "fact_model_drift_daily",
    "watchlist",
    "watchlist_item",
    "ingestion_checkpoint",
}

EXPECTED_PKS = {
    "dim_stock": ["ticker"],
    "fact_price_daily": ["date", "ticker"],
    "fact_investor_flow_daily": ["date", "ticker", "investor_group"],
    "fact_foreign_holding_daily": ["date", "ticker"],
    "fact_features_daily": ["date", "ticker", "feature_version"],
    "fact_ml_prediction_daily": ["date", "ticker", "horizon_days", "model_name"],
    "fact_index_daily": ["date", "index_code"],
    "ml_model_registry": ["model_name", "model_version"],
    "fact_model_drift_daily": ["date", "model_name"],
    "watchlist": ["name"],
    "watchlist_item": ["watchlist_name", "ticker"],
    "ingestion_checkpoint": ["scope_key", "ticker"],
}


def test_create_all_makes_expected_tables(db: Database):
    insp = inspect(db.engine)
    assert EXPECTED_TABLES.issubset(set(insp.get_table_names()))


def test_primary_keys(db: Database):
    insp = inspect(db.engine)
    for table, expected in EXPECTED_PKS.items():
        pk = insp.get_pk_constraint(table)["constrained_columns"]
        assert set(pk) == set(expected), f"{table} PK mismatch: {pk}"


def test_audit_columns_present(db: Database):
    insp = inspect(db.engine)
    for table in ["dim_stock", "fact_price_daily", "fact_investor_flow_daily"]:
        cols = {c["name"] for c in insp.get_columns(table)}
        assert "created_at" in cols and "updated_at" in cols


def test_alembic_baseline_runs_and_matches_orm():
    """Running the Alembic baseline must create the ORM tables (no drift)."""
    from importlib import import_module

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    # Module name starts with a digit, so import via importlib by string.
    migration = import_module(
        "infra.migrations.versions.0001_initial_baseline"
    )
    assert migration.revision == "0001_initial_baseline"
    assert migration.down_revision is None

    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            migration.upgrade()
        conn.commit()
        insp = inspect(conn)
        assert EXPECTED_TABLES.issubset(set(insp.get_table_names()))
