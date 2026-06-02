"""Phase 5: daily pipeline orchestration + data-status endpoint."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from kospi_flow.api import create_app
from kospi_flow.core.config import Settings
from kospi_flow.core.db import Database
from kospi_flow.jobs.daily import retry, run_daily_pipeline


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    base = tmp_path_factory.mktemp("jobs")
    settings = Settings(
        database_url=f"sqlite:///{(base / 'jobs.db').as_posix()}",
        raw_data_path=base / "raw",
        processed_data_path=base / "processed",
    )
    db = Database(settings.database_url)
    db.create_all()
    return db, settings


def test_retry_succeeds_after_failures():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("nope")
        return "ok"

    assert retry(flaky, attempts=3) == "ok"
    assert calls["n"] == 3


def test_retry_raises_after_exhausting():
    with pytest.raises(ValueError):
        retry(lambda: (_ for _ in ()).throw(ValueError("x")), attempts=2)


def test_daily_pipeline_runs_with_training(env):
    db, settings = env
    report = run_daily_pipeline(
        start=date(2021, 1, 4),
        end=date(2022, 12, 30),
        tickers=["005930", "000660", "005380"],
        horizons=(5,),
        train=True,
        database=db,
        settings=settings,
    )
    names = [s.name for s in report.steps]
    assert "ingest" in names and "features" in names
    assert "train_5d" in names and "predict_5d" in names and "validate" in names
    # Ingest/features/predict should all succeed on clean sample data.
    by_name = {s.name: s for s in report.steps}
    assert by_name["ingest"].status == "ok"
    assert by_name["predict_5d"].status == "ok"


def test_data_status_endpoint(env):
    db, settings = env
    # Ensure there is data (pipeline above ran in module scope before this).
    run_daily_pipeline(
        start=date(2021, 1, 4),
        end=date(2021, 6, 30),
        tickers=["005930"],
        horizons=(),
        train=False,
        database=db,
        settings=settings,
    )
    client = TestClient(create_app(database=db))
    resp = client.get("/data-status")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "ok" in data and "counts" in data
    assert data["counts"]["fact_price_daily"] > 0
