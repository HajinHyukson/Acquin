"""End-to-end ingestion with the sample provider, including idempotency."""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, select

from kospi_flow.analytics.pipeline import generate_features
from kospi_flow.core.db import Database
from kospi_flow.core.enums import FreshnessState, InvestorGroup
from kospi_flow.core.models import (
    DimStock,
    FactFeaturesDaily,
    FactForeignHoldingDaily,
    FactInvestorFlowDaily,
    FactPriceDaily,
)
from kospi_flow.data.ingestion import Ingestor
from kospi_flow.data.providers import get_provider

TICKER = "005930"


def _ingestor(db: Database) -> Ingestor:
    provider = get_provider("sample")
    return Ingestor(provider, db, freshness_state=FreshnessState.FINAL_EOD)


def test_run_populates_all_tables(db: Database, date_range, tmp_path, monkeypatch):
    # Redirect raw storage into the temp dir so tests don't touch the repo.
    ing = _ingestor(db)
    monkeypatch.setattr(ing.settings, "raw_data_path", tmp_path / "raw")
    start, end = date_range

    result = ing.run(start, end, tickers=[TICKER])

    assert result.stocks > 0
    assert result.price_rows > 0
    assert result.flow_rows > 0
    assert result.foreign_rows > 0

    with db.session() as s:
        assert s.scalar(select(func.count()).select_from(DimStock)) > 0
        n_price = s.scalar(
            select(func.count()).select_from(FactPriceDaily).where(
                FactPriceDaily.ticker == TICKER
            )
        )
        assert n_price == result.price_rows
        # Three MVP investor groups per price date.
        n_flow = s.scalar(
            select(func.count()).select_from(FactInvestorFlowDaily).where(
                FactInvestorFlowDaily.ticker == TICKER
            )
        )
        assert n_flow == n_price * 3
        assert s.scalar(
            select(func.count()).select_from(FactForeignHoldingDaily).where(
                FactForeignHoldingDaily.ticker == TICKER
            )
        ) == n_price


def test_freshness_state_is_stored(db: Database, date_range, tmp_path, monkeypatch):
    ing = _ingestor(db)
    monkeypatch.setattr(ing.settings, "raw_data_path", tmp_path / "raw")
    start, end = date_range
    ing.run(start, end, tickers=[TICKER])
    with db.session() as s:
        states = s.execute(
            select(FactPriceDaily.freshness_state).distinct()
        ).all()
    assert states == [(FreshnessState.FINAL_EOD.value,)]


def test_ingestion_is_idempotent(db: Database, date_range, tmp_path, monkeypatch):
    ing = _ingestor(db)
    monkeypatch.setattr(ing.settings, "raw_data_path", tmp_path / "raw")
    start, end = date_range

    ing.run(start, end, tickers=[TICKER])
    with db.session() as s:
        first = s.scalar(select(func.count()).select_from(FactPriceDaily))

    # Re-run the same range: counts must not grow (upsert on PK).
    ing.run(start, end, tickers=[TICKER])
    with db.session() as s:
        second = s.scalar(select(func.count()).select_from(FactPriceDaily))

    assert first == second


def test_net_buy_volume_matches_amount_sign(db: Database, date_range):
    """Sanity: foreign net-buy volume and amount agree in sign."""
    provider = get_provider("sample")
    start, end = date_range
    flows = provider.get_investor_flow_daily(TICKER, start, end)
    foreign = [
        f for f in flows if f.investor_group == InvestorGroup.FOREIGN.value
    ]
    assert foreign
    for f in foreign:
        if f.net_buy_amount and f.net_buy_volume:
            assert (f.net_buy_amount > 0) == (f.net_buy_volume > 0)


def test_features_ready_after_ingestion(
    db: Database, date_range, tmp_path, monkeypatch
):
    """Acceptance: at least one stock has price, flow, and feature rows."""
    ing = _ingestor(db)
    monkeypatch.setattr(ing.settings, "raw_data_path", tmp_path / "raw")
    start, end = date_range
    ing.run(start, end, tickers=[TICKER])

    written = generate_features(db, tickers=[TICKER])
    assert written > 0
    with db.session() as s:
        n_feat = s.scalar(
            select(func.count()).select_from(FactFeaturesDaily).where(
                FactFeaturesDaily.ticker == TICKER
            )
        )
    assert n_feat == written
