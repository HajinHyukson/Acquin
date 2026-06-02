"""Phase 5: watchlists, alerts, model registry, drift, scheduler, pipeline."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from kospi_flow.alerts.notifier import (
    Alert,
    FileNotifier,
    NullNotifier,
    get_notifier,
)
from kospi_flow.alerts.rules import evaluate_alerts
from kospi_flow.api import create_app
from kospi_flow.core.config import Settings
from kospi_flow.core.db import Database
from kospi_flow.core.enums import FreshnessState
from kospi_flow.core.models import FactModelDriftDaily, MlModelRegistry, WatchlistItem
from kospi_flow.data.ingestion import Ingestor
from kospi_flow.data.providers import get_provider
from kospi_flow.jobs.daily import run_daily_pipeline
from kospi_flow.jobs.scheduler import DEFAULT_SCHEDULE, due_entries, run_entry
from kospi_flow.ml.drift import build_baseline, compute_drift, feature_psi
from kospi_flow.ml.inference import load_bundle
from kospi_flow.ml.registry import get_active_model, list_models
from kospi_flow.ml.train import train_and_evaluate
from sqlalchemy import func, select

TICKERS = ["005930", "000660", "005380"]


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    base = tmp_path_factory.mktemp("p5")
    settings = Settings(
        database_url=f"sqlite:///{(base / 'p5.db').as_posix()}",
        raw_data_path=base / "raw",
        processed_data_path=base / "processed",
        alert_channel="file",
        alert_log_file="alerts.log",
    )
    db = Database(settings.database_url)
    db.create_all()
    ing = Ingestor(get_provider("sample"), db, settings=settings,
                   freshness_state=FreshnessState.FINAL_EOD)
    ing.run(date(2021, 1, 4), date(2022, 12, 30), tickers=TICKERS)
    return db, settings


# --- notifier -------------------------------------------------------------
def test_file_notifier_writes(tmp_path):
    p = tmp_path / "a.log"
    n = FileNotifier(p)
    assert n.send(Alert("X", "warning", "hi"))
    assert "hi" in p.read_text(encoding="utf-8")


def test_null_notifier_and_factory():
    assert NullNotifier().send(Alert("X", "info", "y")) is True
    s = Settings(alert_channel="none")
    assert get_notifier(s).name == "none"
    s2 = Settings(alert_channel="console")
    assert get_notifier(s2).name == "console"


def test_alert_format_severity():
    assert "CRITICAL" in Alert("C", "critical", "boom").format_text()


# --- scheduler ------------------------------------------------------------
def test_due_entries_matches_minute():
    assert due_entries("18:30") and due_entries("18:30")[0].job == "final_eod"
    assert due_entries("03:00") == []


def test_run_entry_preliminary(env):
    db, settings = env
    entry = next(e for e in DEFAULT_SCHEDULE if e.job == "preliminary")
    report = run_entry(
        entry, database=db, settings=settings, lookback_days=120,
        today=date(2022, 12, 30),
    )
    by = {s.name: s for s in report.steps}
    assert by["ingest"].status == "ok"
    # preliminary entry does not predict.
    assert not any(s.name.startswith("predict") for s in report.steps)


# --- registry + drift -----------------------------------------------------
def test_train_registers_model_and_builds_baseline(env):
    db, settings = env
    report = train_and_evaluate(db, horizon=5, tickers=TICKERS, settings=settings)
    with db.session() as s:
        active = get_active_model(s, report.model_name)
        assert active is not None
        assert active.is_active is True
        assert active.n_samples == report.n_samples
        assert len(list_models(s)) >= 1

    bundle = load_bundle(report.model_name, settings)
    assert bundle["feature_baseline"], "training should store a drift baseline"


def test_psi_helpers():
    import numpy as np
    import pandas as pd

    X = pd.DataFrame({"f": np.linspace(0, 1, 1000)})
    base = build_baseline(X, ["f"], bins=10)
    # Same distribution -> near-zero PSI.
    same = feature_psi(X["f"].to_numpy(), base["f"]["edges"], base["f"]["ref_props"])
    assert same < 0.05
    # Shifted distribution -> larger PSI.
    shifted = feature_psi(
        (X["f"] + 1.0).to_numpy(), base["f"]["edges"], base["f"]["ref_props"]
    )
    assert shifted > same


def test_compute_drift_persists(env):
    db, settings = env
    train_and_evaluate(db, horizon=5, tickers=TICKERS, settings=settings)
    bundle = load_bundle("gbm_return_5d", settings)
    summary = compute_drift(db, bundle, window=20, settings=settings)
    assert summary["status"] in ("ok", "warning", "alert", "unknown", "low_sample")
    with db.session() as s:
        n = s.scalar(select(func.count()).select_from(FactModelDriftDaily))
    assert n >= 1


# --- watchlists API -------------------------------------------------------
@pytest.fixture(scope="module")
def client(env):
    db, _ = env
    return TestClient(create_app(database=db))


def test_watchlist_crud_and_flows(client):
    # create
    r = client.post("/watchlists", json={"name": "tech", "description": "반도체"})
    assert r.status_code == 201, r.text
    # duplicate -> 409
    assert client.post("/watchlists", json={"name": "tech"}).status_code == 409
    # add items
    assert client.post("/watchlists/tech/items", json={"ticker": "005930"}).status_code == 201
    client.post("/watchlists/tech/items", json={"ticker": "000660"})
    # unknown ticker -> 404
    assert client.post("/watchlists/tech/items", json={"ticker": "999999"}).status_code == 404
    # get
    detail = client.get("/watchlists/tech").json()["data"]
    assert set(detail["tickers"]) == {"005930", "000660"}
    # flows view
    flows = client.get("/watchlists/tech/flows").json()["data"]
    assert len(flows) == 2 and "foreign_net_buy" in flows[0]
    # remove + delete
    assert client.delete("/watchlists/tech/items/005930").status_code == 200
    assert client.delete("/watchlists/tech").status_code == 200
    assert client.get("/watchlists/tech").status_code == 404


def test_models_and_drift_endpoints(client, env):
    db, settings = env
    train_and_evaluate(db, horizon=5, tickers=TICKERS, settings=settings)
    compute_drift(db, load_bundle("gbm_return_5d", settings), settings=settings)

    models = client.get("/models").json()["data"]
    assert any(m["model_name"] == "gbm_return_5d" for m in models)
    drift = client.get("/models/gbm_return_5d/drift").json()["data"]
    assert "max_psi" in drift and "status" in drift
    assert client.get("/models/nope/drift").status_code == 404


# --- alert rules ----------------------------------------------------------
def test_watchlist_flow_alert_rule(env):
    db, settings = env
    with db.session() as s:
        if s.get(WatchlistItem, ("alerts_wl", "005930")) is None:
            from kospi_flow.core.models import Watchlist

            if s.get(Watchlist, "alerts_wl") is None:
                s.add(Watchlist(name="alerts_wl"))
            s.add(WatchlistItem(watchlist_name="alerts_wl", ticker="005930"))
    # Very low threshold -> the watchlisted ticker should trigger.
    alerts = evaluate_alerts(db, settings=settings, watchlist_flow_threshold=1.0)
    assert any(a.code == "WATCHLIST_FLOW" for a in alerts)


# --- pipeline integration -------------------------------------------------
def test_daily_pipeline_runs_drift_and_alerts(env):
    db, settings = env
    report = run_daily_pipeline(
        start=date(2021, 1, 4), end=date(2022, 12, 30), tickers=TICKERS,
        horizons=(5,), train=True, database=db, settings=settings,
    )
    names = [s.name for s in report.steps]
    assert "drift_5d" in names
    assert "alerts" in names
    # alerts step should have run without error.
    by = {s.name: s for s in report.steps}
    assert by["alerts"].status == "ok"
    # file notifier should have written alerts (validation clean, but watchlist
    # flow alerts from the previous test's watchlist may fire).
    _ = datetime.now(ZoneInfo(settings.timezone))
