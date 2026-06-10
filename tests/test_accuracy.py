"""Walk-forward backtest storage + prediction-accuracy endpoint."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from kospi_flow.api import create_app
from kospi_flow.core.config import Settings
from kospi_flow.core.db import Database
from kospi_flow.core.enums import FreshnessState
from kospi_flow.core.models import FactMlPredictionDaily
from kospi_flow.data.ingestion import Ingestor
from kospi_flow.data.providers import get_provider
from kospi_flow.ml.backtest import (
    BACKTEST_PREFIX,
    backtest_model_name,
    walk_forward_backtest,
)
from kospi_flow.ml.inference import predict_and_store
from kospi_flow.ml.train import train_and_evaluate

TICKERS = ["005930", "000660"]


@pytest.fixture(scope="module")
def bt_env(tmp_path_factory) -> tuple[Database, Settings]:
    """~2 years of sample data; isolated from other modules' fixtures."""
    base = tmp_path_factory.mktemp("bt")
    settings = Settings(
        database_url=f"sqlite:///{(base / 'bt.db').as_posix()}",
        raw_data_path=base / "raw",
        processed_data_path=base / "processed",
    )
    db = Database(settings.database_url)
    db.create_all()
    ing = Ingestor(
        get_provider("sample"),
        db,
        settings=settings,
        freshness_state=FreshnessState.FINAL_EOD,
    )
    ing.run(date(2021, 1, 4), date(2022, 12, 29), tickers=TICKERS)
    walk_forward_backtest(
        db, horizon=5, tickers=TICKERS, n_splits=3, min_train=60, settings=settings
    )
    return db, settings


def test_backtest_stores_prefixed_oos_rows(bt_env):
    db, _ = bt_env
    with db.session() as s:
        stored_name = backtest_model_name("gbm_return_5d")
        n = s.scalar(
            select(func.count())
            .select_from(FactMlPredictionDaily)
            .where(FactMlPredictionDaily.model_name == stored_name)
        )
        assert n and n > 0
        # Multiple historical dates covered (not just the latest one).
        n_dates = s.scalar(
            select(func.count(func.distinct(FactMlPredictionDaily.date))).where(
                FactMlPredictionDaily.model_name == stored_name
            )
        )
        assert n_dates > 50


def test_backtest_rerun_replaces_not_duplicates(bt_env):
    db, settings = bt_env
    with db.session() as s:
        before = s.scalar(select(func.count()).select_from(FactMlPredictionDaily))
    walk_forward_backtest(
        db, horizon=5, tickers=TICKERS, n_splits=3, min_train=60, settings=settings
    )
    with db.session() as s:
        after = s.scalar(select(func.count()).select_from(FactMlPredictionDaily))
    assert after == before


def test_accuracy_endpoint_summary_and_rows(bt_env):
    db, _ = bt_env
    client = TestClient(create_app(database=db))
    resp = client.get("/stocks/005930/prediction-accuracy?horizon=5")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    s = data["summary"]
    assert s["n"] == len(data["rows"])
    assert 0.0 <= s["direction_hit_rate"] <= 1.0
    assert 0.0 <= s["band_coverage"] <= 1.0
    assert s["mae"] >= 0.0

    row = data["rows"][0]
    assert row["target_date"] > row["date"]  # outcome strictly after prediction
    assert row["p10_return"] <= row["p90_return"] + 1e-9
    assert isinstance(row["direction_hit"], bool)
    assert data["rolling_hit_rate"]  # rolling series present


def test_accuracy_404_when_no_history(bt_env):
    db, _ = bt_env
    client = TestClient(create_app(database=db))
    # No backtest was run for horizon=20.
    assert client.get("/stocks/005930/prediction-accuracy?horizon=20").status_code == 404
    assert client.get("/stocks/999999/prediction-accuracy").status_code == 404


def test_live_endpoints_exclude_backtest_rows(bt_env):
    db, settings = bt_env
    # Train + store live predictions; backtest rows already exist.
    train_and_evaluate(db, horizon=5, tickers=TICKERS, n_splits=3, settings=settings)
    predict_and_store(db, "gbm_return_5d", tickers=TICKERS, settings=settings)

    client = TestClient(create_app(database=db))
    proj = client.get("/stocks/005930/projection").json()["data"]
    for group in proj["models"]:
        for p in group["projections"]:
            assert not p["model_name"].startswith(BACKTEST_PREFIX)
    assert proj["projections"]  # back-compat shape intact

    picks = client.get("/market/top-picks?horizon=5&notable_only=false").json()["data"]
    assert picks  # ranking still works with backtest rows present
    assert len(picks) <= len(TICKERS)
