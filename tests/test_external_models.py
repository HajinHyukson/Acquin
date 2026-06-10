"""External-model prediction socket: auth, ingest, and projection grouping."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from kospi_flow.api import create_app
from kospi_flow.core.config import Settings
from kospi_flow.core.db import Database
from kospi_flow.core.models import DimStock, FactPriceDaily

KEY = "test-ingest-key"


def _payload(ticker: str = "005930", n: int = 1) -> dict:
    return {
        "model_version": "v1",
        "predictions": [
            {
                "date": date(2021, 1, 4 + i).isoformat(),
                "ticker": ticker,
                "horizon_days": 5,
                "predicted_return": 0.01 * (i + 1),
                "predicted_return_p10": -0.02,
                "predicted_return_p50": 0.01,
                "predicted_return_p90": 0.04,
                "prob_outperform_kospi": 0.6,
            }
            for i in range(n)
        ],
    }


@pytest.fixture()
def client_db(tmp_path) -> tuple[TestClient, Database]:
    # File-backed DB: the in-memory fixture is not visible across the
    # TestClient worker thread's separate connection.
    db = Database(f"sqlite:///{(tmp_path / 'ext.db').as_posix()}")
    db.create_all()
    with db.session() as s:
        s.add(DimStock(ticker="005930", name_kr="삼성전자"))
        s.add(
            FactPriceDaily(date=date(2021, 1, 4), ticker="005930", close=80000.0)
        )
    settings = Settings(ingest_api_key=KEY)
    return TestClient(create_app(settings=settings, database=db)), db


def test_ingest_disabled_without_configured_key(db: Database):
    client = TestClient(create_app(settings=Settings(), database=db))
    resp = client.post("/models/sentiment_v1/predictions", json=_payload())
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "INGEST_DISABLED"


def test_ingest_rejects_bad_key(client_db):
    client, _ = client_db
    resp = client.post(
        "/models/sentiment_v1/predictions",
        json=_payload(),
        headers={"X-API-Key": "wrong"},
    )
    assert resp.status_code == 401
    assert client.post("/models/sentiment_v1/predictions", json=_payload()).status_code == 401


def test_ingest_rejects_reserved_names(client_db):
    client, _ = client_db
    for name in ("gbm_return_5d", "wf::anything"):
        resp = client.post(
            f"/models/{name}/predictions",
            json=_payload(),
            headers={"X-API-Key": KEY},
        )
        assert resp.status_code == 422, name
        assert resp.json()["error"]["code"] == "RESERVED_MODEL_NAME"


def test_ingest_stores_registers_and_projects(client_db):
    client, db = client_db
    resp = client.post(
        "/models/sentiment_v1/predictions",
        json=_payload(n=2),
        headers={"X-API-Key": KEY},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["stored"] == 2
    assert body["skipped_unknown_tickers"] == []

    # Listed in the registry as an external model.
    models = client.get("/models").json()["data"]
    ext = [m for m in models if m["model_name"] == "sentiment_v1"]
    assert ext and ext[0]["backend"] == "external"

    # Projection groups the external model; ?model= features it.
    proj = client.get("/stocks/005930/projection").json()["data"]
    assert any(g["model"] == "sentiment_v1" and g["source"] == "external" for g in proj["models"])
    featured = client.get("/stocks/005930/projection?model=sentiment_v1").json()["data"]
    assert featured["model"] == "sentiment_v1"
    assert featured["projections"][0]["horizon_days"] == 5

    # Re-posting the same rows upserts (no duplicate-key failure).
    again = client.post(
        "/models/sentiment_v1/predictions",
        json=_payload(n=2),
        headers={"X-API-Key": KEY},
    )
    assert again.status_code == 200
    assert again.json()["data"]["stored"] == 2


def test_ingest_skips_unknown_tickers(client_db):
    client, _ = client_db
    resp = client.post(
        "/models/sentiment_v1/predictions",
        json=_payload(ticker="999999"),
        headers={"X-API-Key": KEY},
    )
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["stored"] == 0
    assert body["skipped_unknown_tickers"] == ["999999"]
