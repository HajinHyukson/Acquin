"""Step 2: market-index data path + benchmark (real index vs proxy fallback)."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from kospi_flow.analytics.market import (
    benchmark_return_series,
    benchmark_source,
    has_index,
    index_return_series,
    market_return_series,
    load_price_panel,
)
from kospi_flow.api import create_app
from kospi_flow.core.db import Database
from kospi_flow.core.enums import FreshnessState
from kospi_flow.core.models import FactIndexDaily
from kospi_flow.data.ingestion import Ingestor
from kospi_flow.data.providers import get_provider

TICKERS = ["005930", "000660", "005380"]
RANGE = (date(2021, 1, 4), date(2021, 6, 30))


def _ingestor(db, tmp_path):
    ing = Ingestor(get_provider("sample"), db, freshness_state=FreshnessState.FINAL_EOD)
    ing.settings.raw_data_path = tmp_path / "raw"
    return ing


def test_sample_provider_emits_index():
    rows = get_provider("sample").get_index_ohlcv("1001", *RANGE)
    assert rows
    assert rows[0].index_code == "1001"
    assert rows[0].name == "코스피"
    assert rows[0].close > 0
    # First row has no prior day -> return_1d None; later rows populated.
    assert rows[0].return_1d is None
    assert rows[5].return_1d is not None


@pytest.fixture
def db_with_index(tmp_path):
    # File-backed so the TestClient's worker thread shares the same DB.
    db = Database(f"sqlite:///{(tmp_path / 'idx.db').as_posix()}")
    db.create_all()
    ing = _ingestor(db, tmp_path)
    ing.run(*RANGE, tickers=TICKERS)  # include_index defaults True
    return db


@pytest.fixture
def db_no_index(tmp_path):
    db = Database(f"sqlite:///{(tmp_path / 'noidx.db').as_posix()}")
    db.create_all()
    ing = _ingestor(db, tmp_path)
    ing.run(*RANGE, tickers=TICKERS, include_index=False)
    return db


def test_ingestion_populates_index(db_with_index):
    with db_with_index.session() as s:
        n = s.scalar(select(func.count()).select_from(FactIndexDaily))
        assert n > 0
        assert has_index(s)
        assert benchmark_source(s) == "index:1001"


def test_benchmark_uses_real_index_when_present(db_with_index):
    with db_with_index.session() as s:
        bench = benchmark_return_series(s)
        idx = index_return_series(s)
        proxy = market_return_series(load_price_panel(s))
        # Benchmark must equal the index series, not the cap-weighted proxy.
        assert bench.equals(idx)
        assert not bench.reindex(proxy.index).equals(proxy)


def test_benchmark_falls_back_to_proxy(db_no_index):
    with db_no_index.session() as s:
        assert not has_index(s)
        assert benchmark_source(s) == "proxy"
        bench = benchmark_return_series(s)
        proxy = market_return_series(load_price_panel(s))
        assert bench.equals(proxy)


def test_market_overview_reports_index(db_with_index):
    client = TestClient(create_app(database=db_with_index))
    data = client.get("/market/overview").json()["data"]
    assert data["benchmark_source"] == "index:1001"
    assert data["index_level"] is not None
    assert data["market_return_1d"] is not None


def test_market_index_endpoint(db_with_index):
    client = TestClient(create_app(database=db_with_index))
    body = client.get("/market/index").json()
    rows = body["data"]
    assert rows and "close" in rows[0]
    assert body["metadata"]["benchmark_source"] == "index:1001"


def test_market_index_endpoint_proxy_when_no_index(db_no_index):
    client = TestClient(create_app(database=db_no_index))
    body = client.get("/market/index").json()
    assert body["metadata"]["benchmark_source"] == "proxy"
    assert body["data"]  # proxy level series still returned
