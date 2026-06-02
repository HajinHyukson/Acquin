"""API endpoint tests (Phase 2)."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from kospi_flow.analytics.pipeline import generate_features
from kospi_flow.api import create_app
from kospi_flow.core.db import Database
from kospi_flow.core.enums import FreshnessState
from kospi_flow.data.ingestion import Ingestor
from kospi_flow.data.providers import get_provider

TICKER = "005930"


@pytest.fixture(scope="module")
def seeded_db(tmp_path_factory) -> Database:
    """File-backed SQLite seeded with sample data + features (module scope)."""
    path = tmp_path_factory.mktemp("api") / "api.db"
    db = Database(f"sqlite:///{path.as_posix()}")
    db.create_all()
    ing = Ingestor(
        get_provider("sample"), db, freshness_state=FreshnessState.FINAL_EOD
    )
    ing.settings.raw_data_path = tmp_path_factory.mktemp("raw")
    ing.run(date(2021, 1, 4), date(2021, 6, 30))
    generate_features(db)
    return db


@pytest.fixture(scope="module")
def client(seeded_db) -> TestClient:
    return TestClient(create_app(database=seeded_db))


def _data(resp):
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "data" in body and "metadata" in body
    assert "generated_at" in body["metadata"]
    return body["data"]


def test_health(client):
    assert _data(client.get("/health"))["status"] == "ok"


def test_data_freshness(client):
    data = _data(client.get("/metadata/data-freshness"))
    assert data["fact_price_daily"]["freshness_state"] == "FINAL_EOD"
    assert data["fact_price_daily"]["row_count"] > 0


def test_list_stocks(client):
    data = _data(client.get("/stocks"))
    tickers = {s["ticker"] for s in data}
    assert TICKER in tickers


def test_stock_detail_returns(client):
    data = _data(client.get(f"/stocks/{TICKER}"))
    assert data["ticker"] == TICKER
    assert "return_5d" in data and "close" in data


def test_stock_price_range(client):
    data = _data(client.get(f"/stocks/{TICKER}/price?start=2021-02-01&end=2021-02-28"))
    assert data
    assert all("2021-02" in row["date"] for row in data)


def test_investor_flows_cumulative(client):
    data = _data(client.get(f"/stocks/{TICKER}/investor-flows?cumulative=true"))
    foreign = data["by_group"]["foreign"]
    assert "cumulative_net_buy_amount" in foreign[0]


def test_foreign_holdings(client):
    data = _data(client.get(f"/stocks/{TICKER}/foreign-holdings"))
    assert data
    assert 0.0 <= data[-1]["foreign_ownership_pct"] <= 1.0


def test_features_endpoint(client):
    data = _data(client.get(f"/stocks/{TICKER}/features"))
    assert "foreign_net_5d_amt" in data[0]


def test_unknown_ticker_error_envelope(client):
    resp = client.get("/stocks/999999")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "DATA_NOT_AVAILABLE"


def test_market_overview(client):
    data = _data(client.get("/market/overview"))
    assert data["n_stocks"] > 0
    assert data["market_return_1d"] is not None


def test_top_net_buy(client):
    data = _data(client.get("/market/top-net-buy?investor_group=foreign&lookback_days=5"))
    assert data
    assert data[0]["rank"] == 1
    # Sorted descending by net-buy amount.
    amounts = [r["net_buy_amount"] for r in data]
    assert amounts == sorted(amounts, reverse=True)


def test_closes_endpoint(client):
    data = _data(client.get(f"/market/closes?days=10&tickers={TICKER},000660"))
    assert TICKER in data
    assert isinstance(data[TICKER], list) and len(data[TICKER]) > 0


def test_top_picks_empty_without_predictions(client):
    # The api fixture seeds prices/flows/features but no model predictions.
    data = _data(client.get("/market/top-picks?horizon=5"))
    assert data == []


def test_screener_investor_flow(client):
    resp = client.post(
        "/screeners/investor-flow",
        json={"lookback_days": 5, "investor_groups": ["foreign"], "limit": 10},
    )
    data = _data(resp)
    assert isinstance(data, list)
    if data:
        assert "net_buy_pct_mcap" in data[0]


def test_screener_min_amount_filters(client):
    huge = 1e18  # impossibly large threshold -> no results
    resp = client.post(
        "/screeners/investor-flow",
        json={"lookback_days": 5, "min_net_buy_amount": huge},
    )
    assert _data(resp) == []


def test_correlations_endpoint(client):
    data = _data(client.get(f"/stocks/{TICKER}/correlations?investor_groups=foreign"))
    assert isinstance(data, list) and data
    row = data[0]
    assert {"investor_group", "flow_window", "horizon", "n"}.issubset(row)


def test_events_endpoint(client):
    data = _data(
        client.get(f"/stocks/{TICKER}/events?event_type=institution_accumulation")
    )
    assert "results" in data and "matching_dates" in data
    assert len(data["results"]) == 5  # one per horizon


def test_events_unknown_type(client):
    resp = client.get(f"/stocks/{TICKER}/events?event_type=nope")
    assert resp.status_code == 404


def test_flow_return_profile_endpoint(client):
    data = _data(client.get(f"/stocks/{TICKER}/flow-return-profile?flow_window=5"))
    assert data["flow_window"] == 5
    assert "foreign" in data["groups"]
    fg = data["groups"]["foreign"]["quintiles"]
    # Either 5 buckets, or an explicit insufficient-data note.
    assert len(fg) in (0, 5)
    if fg:
        assert "5" in fg[0]["mean_return"]
