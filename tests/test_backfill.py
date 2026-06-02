"""Resumable backfill (for wide real-data loads with session timeouts)."""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, select

from kospi_flow.core.db import Database
from kospi_flow.core.enums import FreshnessState
from kospi_flow.core.models import FactPriceDaily, IngestionCheckpoint
from kospi_flow.data.ingestion import Ingestor, chunked_date_ranges
from kospi_flow.data.providers import get_provider

TICKERS = ["005930", "000660"]
START, END = date(2021, 1, 4), date(2021, 6, 30)


def test_chunked_date_ranges_cover_without_overlap():
    chunks = chunked_date_ranges(date(2021, 1, 1), date(2021, 12, 31), 90)
    assert chunks[0][0] == date(2021, 1, 1)
    assert chunks[-1][1] == date(2021, 12, 31)
    for (s, e) in chunks:
        assert (e - s).days <= 89
    for (prev, nxt) in zip(chunks, chunks[1:]):
        assert (nxt[0] - prev[1]).days == 1


def _ingestor(db, tmp_path):
    ing = Ingestor(get_provider("sample"), db, freshness_state=FreshnessState.FINAL_EOD)
    ing.settings.raw_data_path = tmp_path / "raw"
    return ing


def test_backfill_loads_and_checkpoints(tmp_path):
    db = Database("sqlite:///:memory:")
    db.create_all()
    ing = _ingestor(db, tmp_path)

    r1 = ing.backfill(START, END, tickers=TICKERS)
    assert r1.price_rows > 0 and r1.index_rows > 0
    with db.session() as s:
        rows = s.scalar(select(func.count()).select_from(FactPriceDaily))
        # Each ticker + the index pseudo-ticker are checkpointed as done.
        done = s.scalar(
            select(func.count()).select_from(IngestionCheckpoint)
            .where(IngestionCheckpoint.status == "done")
        )
    assert rows == r1.price_rows
    assert done == len(TICKERS) + 1  # tickers + __index__


def test_backfill_resumes_and_skips_completed(tmp_path):
    """A second run with all tickers already done re-fetches nothing."""
    db = Database("sqlite:///:memory:")
    db.create_all()
    ing = _ingestor(db, tmp_path)

    ing.backfill(START, END, tickers=TICKERS)
    with db.session() as s:
        first = s.scalar(select(func.count()).select_from(FactPriceDaily))

    # Re-run identical command: everything is checkpointed → 0 new price rows
    # fetched this pass, and DB row count is unchanged (no duplicates).
    r2 = ing.backfill(START, END, tickers=TICKERS)
    assert r2.price_rows == 0  # all tickers skipped as already done
    with db.session() as s:
        second = s.scalar(select(func.count()).select_from(FactPriceDaily))
    assert second == first


def test_backfill_only_processes_pending(tmp_path):
    """If one ticker is already done, the next run only does the other."""
    db = Database("sqlite:///:memory:")
    db.create_all()
    ing = _ingestor(db, tmp_path)

    ing.backfill(START, END, tickers=["005930"])  # only the first ticker
    # Now ask for both; 005930 is done, so only 000660 is fetched.
    r = ing.backfill(START, END, tickers=TICKERS)
    with db.session() as s:
        n_005930 = s.scalar(
            select(func.count()).select_from(FactPriceDaily)
            .where(FactPriceDaily.ticker == "005930")
        )
    assert r.price_rows > 0  # 000660 fetched
    # 005930 still present (not re-fetched, not lost).
    assert n_005930 > 0


def test_backfill_restart_clears_checkpoints(tmp_path):
    db = Database("sqlite:///:memory:")
    db.create_all()
    ing = _ingestor(db, tmp_path)

    ing.backfill(START, END, tickers=TICKERS)
    # restart=True wipes progress, so it re-fetches (price_rows > 0 again).
    r = ing.backfill(START, END, tickers=TICKERS, restart=True)
    assert r.price_rows > 0
