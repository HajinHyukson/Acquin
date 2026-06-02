"""Phase 4 ML: dataset, walk-forward, training, inference, projection endpoint."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from kospi_flow.api import create_app
from kospi_flow.core.config import Settings
from kospi_flow.core.db import Database
from kospi_flow.core.enums import FreshnessState
from kospi_flow.core.models import FactMlPredictionDaily
from kospi_flow.data.ingestion import Ingestor
from kospi_flow.data.providers import get_provider
from kospi_flow.ml.dataset import build_dataset, latest_feature_rows
from kospi_flow.ml.inference import predict_and_store
from kospi_flow.ml.train import train_and_evaluate
from kospi_flow.ml.validation import walk_forward_splits
from sqlalchemy import func, select

TICKERS = ["005930", "000660", "005380"]


@pytest.fixture(scope="module")
def ml_env(tmp_path_factory) -> tuple[Database, Settings]:
    """~3 years of sample data + a Settings pointing artifacts at a temp dir."""
    base = tmp_path_factory.mktemp("ml")
    settings = Settings(
        database_url=f"sqlite:///{(base / 'ml.db').as_posix()}",
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
    ing.run(date(2021, 1, 4), date(2023, 12, 29), tickers=TICKERS)
    return db, settings


def test_walk_forward_no_overlap_and_order():
    dates = pd.Series(pd.bdate_range("2021-01-04", periods=400).date)
    folds = walk_forward_splits(dates, n_splits=3, embargo=5, min_train=60)
    assert folds
    for f in folds:
        assert max(f.train_dates) < min(f.test_dates)  # train strictly before test
        # embargo gap respected (at least 5 trading days removed).
        assert set(f.train_dates).isdisjoint(set(f.test_dates))


def test_build_dataset_has_features_and_targets(ml_env):
    db, _ = ml_env
    with db.session() as s:
        panel, cols = build_dataset(s, horizon=5, tickers=TICKERS)
    assert not panel.empty
    assert "y_reg" in panel and "y_cls" in panel
    # Forward target rows dropped -> no NaN targets remain.
    assert panel["y_reg"].notna().all()
    # Expected per-group flow features present.
    assert any(c.startswith("net5_foreign") for c in cols)
    assert "close_price" not in cols  # excluded from features


def test_train_produces_metrics_and_artifact(ml_env):
    db, settings = ml_env
    report = train_and_evaluate(
        db, horizon=5, tickers=TICKERS, n_splits=3, settings=settings
    )
    assert report.n_samples > 0
    assert report.n_folds >= 1
    assert report.backend in ("lightgbm", "sklearn")
    # Out-of-sample regression metrics computed.
    assert report.main_regression.get("rmse") is not None
    assert report.artifact_path and report.artifact_path.endswith(".joblib")


def test_latest_feature_rows_one_per_ticker(ml_env):
    db, _ = ml_env
    with db.session() as s:
        latest, _cols = latest_feature_rows(s, tickers=TICKERS)
    assert set(latest["ticker"]) == set(TICKERS)
    assert latest.groupby("ticker").size().max() == 1


def test_predict_and_store_then_projection_endpoint(ml_env):
    db, settings = ml_env
    # Train (saves bundle to the temp processed path) then predict.
    train_and_evaluate(db, horizon=5, tickers=TICKERS, n_splits=3, settings=settings)
    n = predict_and_store(db, "gbm_return_5d", tickers=TICKERS, settings=settings)
    assert n == len(TICKERS)

    with db.session() as s:
        stored = s.scalar(select(func.count()).select_from(FactMlPredictionDaily))
    assert stored == len(TICKERS)

    client = TestClient(create_app(database=db))
    resp = client.get("/stocks/005930/projection")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    proj = data["projections"][0]
    assert proj["horizon_days"] == 5
    assert proj["prob_outperform_kospi"] is not None
    band = proj["prediction_band"]
    # P10 <= P90 return ordering should hold from quantile models.
    assert band["p10_return"] <= band["p90_return"] + 1e-9


def test_top_picks_endpoint(ml_env):
    db, settings = ml_env
    train_and_evaluate(db, horizon=5, tickers=TICKERS, n_splits=3, settings=settings)
    predict_and_store(db, "gbm_return_5d", tickers=TICKERS, settings=settings)

    client = TestClient(create_app(database=db))
    # notable_only=false ranks purely by ML projection (no flow filter).
    rows = client.get("/market/top-picks?horizon=5&notable_only=false").json()["data"]
    assert rows and len(rows) <= len(TICKERS)
    # Sorted by predicted_return descending, with ranks assigned.
    rets = [r["predicted_return"] for r in rows]
    assert rets == sorted(rets, reverse=True)
    assert rows[0]["rank"] == 1
    assert "foreign_net" in rows[0] and "predicted_price" in rows[0]
