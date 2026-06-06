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


def test_retrain_all_syncs_bundles_and_metrics(tmp_path):
    from kospi_flow.core.enums import FreshnessState
    from kospi_flow.data.ingestion import Ingestor
    from kospi_flow.data.providers import get_provider
    from kospi_flow.jobs.retrain import retrain_all

    tickers = ["005930", "000660", "005380"]
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'r.db').as_posix()}",
        raw_data_path=tmp_path / "raw",
        processed_data_path=tmp_path / "processed",
    )
    db = Database(settings.database_url)
    db.create_all()
    Ingestor(
        get_provider("sample"), db, settings=settings,
        freshness_state=FreshnessState.FINAL_EOD,
    ).run(date(2021, 1, 4), date(2022, 12, 30), tickers=tickers)

    repo_models = tmp_path / "repo_models"  # stand-in for the committed models/ dir
    result = retrain_all(
        horizons=[5, 20], tickers=tickers, model_version="v2026-06-09",
        repo_models_dir=repo_models, database=db, settings=settings,
    )

    assert result.model_version == "v2026-06-09"
    assert {r.horizon for r in result.reports} == {5, 20}
    # Each horizon's bundle copied into the (tmp) committed models dir.
    assert (repo_models / "gbm_return_5d.joblib").exists()
    assert (repo_models / "gbm_return_20d.joblib").exists()
    assert set(result.synced) == {"gbm_return_5d.joblib", "gbm_return_20d.joblib"}
    # Durable metrics history: one row per horizon for this run.
    csv_path = repo_models / "metrics_history.csv"
    lines = csv_path.read_text(encoding="utf-8").strip().splitlines()
    assert lines[0].startswith("date,model_name,model_version,horizon,")
    assert len(lines) - 1 == 2
    assert all("v2026-06-09" in line for line in lines[1:])


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
