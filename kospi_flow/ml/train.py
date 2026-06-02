"""Walk-forward training and evaluation (context doc §11.4–11.6).

Trains the baseline and main models with time-based walk-forward folds, reports
out-of-sample metrics (incl. Daily Spearman IC / ICIR), then fits final models
on all available data and saves a model bundle for inference.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from kospi_flow.core.config import Settings, get_settings
from kospi_flow.core.db import Database
from kospi_flow.core.logging import get_logger
from kospi_flow.ml import metrics as M
from kospi_flow.ml.dataset import FEATURE_VERSION, build_dataset
from kospi_flow.ml.models import (
    backend_name,
    make_baseline_regressor,
    make_classifier,
    make_quantile_regressor,
    make_regressor,
)
from kospi_flow.ml.validation import split_panel, walk_forward_splits

logger = get_logger(__name__)


@dataclass
class TrainReport:
    model_name: str
    model_version: str
    feature_version: str
    horizon: int
    backend: str
    n_samples: int
    n_folds: int
    baseline_regression: dict = field(default_factory=dict)
    main_regression: dict = field(default_factory=dict)
    classification: dict = field(default_factory=dict)
    mean_ic: float | None = None
    icir: float | None = None
    artifact_path: str | None = None
    trained_at: str | None = None

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def model_dir(settings: Settings) -> Path:
    path = settings.processed_data_path / "models"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _agg(metric_dicts: list[dict]) -> dict:
    """Average a list of metric dicts (None-safe)."""
    keys = {k for d in metric_dicts for k in d}
    out: dict = {}
    for k in keys:
        vals = [d[k] for d in metric_dicts if d.get(k) is not None]
        out[k] = float(np.mean(vals)) if vals else None
    return out


def train_and_evaluate(
    database: Database,
    horizon: int = 5,
    tickers: list[str] | None = None,
    n_splits: int = 3,
    model_name: str | None = None,
    model_version: str = "v001",
    settings: Settings | None = None,
    save: bool = True,
) -> TrainReport:
    settings = settings or get_settings()
    model_name = model_name or f"gbm_return_{horizon}d"

    with database.session() as s:
        panel, feature_cols = build_dataset(s, horizon, tickers)

    if panel.empty or not feature_cols:
        raise ValueError("No training data available; ingest data first.")

    folds = walk_forward_splits(panel["date"], n_splits=n_splits, embargo=horizon)
    base_reg_m, main_reg_m, cls_m = [], [], []
    oos_dates, oos_true, oos_pred = [], [], []

    for i, fold in enumerate(folds):
        train, test = split_panel(panel, fold)
        if train.empty or test.empty:
            continue
        Xtr, Xte = train[feature_cols], test[feature_cols]
        ytr, yte = train["y_reg"].to_numpy(), test["y_reg"].to_numpy()

        base = make_baseline_regressor().fit(Xtr, ytr)
        main = make_regressor().fit(Xtr, ytr)
        base_reg_m.append(M.regression_metrics(yte, base.predict(Xte)))
        pred = main.predict(Xte)
        main_reg_m.append(M.regression_metrics(yte, pred))

        clf = make_classifier().fit(Xtr, train["y_cls"].to_numpy())
        prob = clf.predict_proba(Xte)[:, 1]
        cls_m.append(M.classification_metrics(test["y_cls"].to_numpy(), prob))

        oos_dates.append(test["date"])
        oos_true.append(yte)
        oos_pred.append(pred)
        logger.info("Fold %d: train=%d test=%d", i + 1, len(train), len(test))

    mean_ic = icir = None
    if oos_dates:
        d = pd.concat(oos_dates, ignore_index=True)
        mean_ic, icir, _ = M.daily_ic(
            d, np.concatenate(oos_true), np.concatenate(oos_pred)
        )

    report = TrainReport(
        model_name=model_name,
        model_version=model_version,
        feature_version=FEATURE_VERSION,
        horizon=horizon,
        backend=backend_name(),
        n_samples=int(len(panel)),
        n_folds=len(folds),
        baseline_regression=_agg(base_reg_m),
        main_regression=_agg(main_reg_m),
        classification=_agg(cls_m),
        mean_ic=mean_ic,
        icir=icir,
    )

    report.trained_at = datetime.now().isoformat(timespec="seconds")

    if save:
        # Final fit on all data for inference, plus quantile band models.
        from kospi_flow.ml.drift import build_baseline
        from kospi_flow.ml.registry import register_model

        X, y = panel[feature_cols], panel["y_reg"].to_numpy()
        bundle = {
            "regressor": make_regressor().fit(X, y),
            "classifier": make_classifier().fit(X, panel["y_cls"].to_numpy()),
            "quantiles": {
                q: make_quantile_regressor(q).fit(X, y) for q in (0.1, 0.5, 0.9)
            },
            "feature_cols": feature_cols,
            # Binned training-feature distribution for drift monitoring.
            "feature_baseline": build_baseline(X, feature_cols),
            "horizon": horizon,
            "model_name": model_name,
            "model_version": model_version,
            "feature_version": FEATURE_VERSION,
            "backend": backend_name(),
            "trained_at": report.trained_at,
        }
        path = model_dir(settings) / f"{model_name}.joblib"
        joblib.dump(bundle, path)
        report.artifact_path = str(path)
        logger.info("Saved model bundle to %s", path)
        register_model(database, report, make_active=True)

    logger.info(
        "Train report: backend=%s n=%d folds=%d IC=%s",
        report.backend,
        report.n_samples,
        report.n_folds,
        f"{mean_ic:.3f}" if mean_ic is not None else "n/a",
    )
    return report
