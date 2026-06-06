"""Walk-forward training and evaluation (context doc §11.4–11.6).

Trains the baseline and main models with time-based walk-forward folds, reports
out-of-sample metrics (incl. Daily Spearman IC / ICIR), then fits final models
on all available data and saves a model bundle for inference.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date, datetime
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
    train_window_days: int | None = None

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def model_dir(settings: Settings) -> Path:
    path = settings.processed_data_path / "models"
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_model_version() -> str:
    """Date-stamped version (``vYYYYMMDD``).

    Used when no explicit version is given so each retrain registers a *distinct*
    ``ml_model_registry`` row (and metrics-history line) instead of overwriting
    the previous one — see context doc §24.3 / §25 Phase A. The deployed inference
    bundle still overwrites the same ``<model_name>.joblib`` filename; only the
    performance record accumulates.
    """
    return f"v{date.today():%Y%m%d}"


#: Columns of the human-readable performance log appended on every retrain.
METRICS_HISTORY_HEADER = [
    "date",
    "model_name",
    "model_version",
    "horizon",
    "mean_ic",
    "icir",
    "directional_accuracy",
    "auc",
    "rmse",
    "mae",
    "n_samples",
    "backend",
    "trained_at",
]


def append_metrics_history(path: Path, report: "TrainReport") -> None:
    """Append one out-of-sample metrics row per retrain (KB-scale; §24.3).

    Lives next to the model bundles (``<processed>/models/metrics_history.csv``)
    so the retrain→commit step carries it into the committed ``models/`` dir. The
    file is diff-friendly and needs no DB connection to inspect history.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "date": (report.trained_at or "")[:10],
        "model_name": report.model_name,
        "model_version": report.model_version,
        "horizon": report.horizon,
        "mean_ic": report.mean_ic,
        "icir": report.icir,
        "directional_accuracy": report.main_regression.get("directional_accuracy"),
        "auc": report.classification.get("auc"),
        "rmse": report.main_regression.get("rmse"),
        "mae": report.main_regression.get("mae"),
        "n_samples": report.n_samples,
        "backend": report.backend,
        "trained_at": report.trained_at,
    }
    write_header = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=METRICS_HISTORY_HEADER)
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def _trailing_window(panel: pd.DataFrame, window_days: int | None) -> pd.DataFrame:
    """Keep only rows within the last ``window_days`` trading dates.

    ``None`` (or 0) returns the panel unchanged. Used for the final inference fit
    so the deployed model tracks the current regime rather than all history
    (context doc §24.1 / §25 Phase B).
    """
    if not window_days:
        return panel
    unique = sorted(pd.Series(panel["date"]).dropna().unique())
    if len(unique) <= window_days:
        return panel
    keep = set(unique[-window_days:])
    return panel[panel["date"].isin(keep)].reset_index(drop=True)


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
    model_version: str | None = None,
    settings: Settings | None = None,
    save: bool = True,
) -> TrainReport:
    settings = settings or get_settings()
    model_name = model_name or f"gbm_return_{horizon}d"
    # A distinct (date-stamped) version per retrain so the registry + metrics
    # history accumulate rather than overwrite (§24.3 / §25 Phase A).
    model_version = model_version or default_model_version()

    with database.session() as s:
        panel, feature_cols = build_dataset(s, horizon, tickers)

    if panel.empty or not feature_cols:
        raise ValueError("No training data available; ingest data first.")

    folds = walk_forward_splits(
        panel["date"],
        n_splits=n_splits,
        embargo=horizon,
        train_window=settings.train_window_days,
    )
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
    report.train_window_days = settings.train_window_days

    if save:
        # Final fit on all data for inference, plus quantile band models.
        from kospi_flow.ml.drift import build_baseline
        from kospi_flow.ml.registry import register_model

        # Fit on a trailing window (regime-tracking) when configured; else all
        # history. The drift baseline is built from the SAME rows the model was
        # fit on, so PSI compares live features against that window (§24.1).
        fit_panel = _trailing_window(panel, settings.train_window_days)
        X, y = fit_panel[feature_cols], fit_panel["y_reg"].to_numpy()
        bundle = {
            "regressor": make_regressor().fit(X, y),
            "classifier": make_classifier().fit(X, fit_panel["y_cls"].to_numpy()),
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
            "train_window_days": settings.train_window_days,
            "fit_date_start": str(fit_panel["date"].min()),
            "fit_date_end": str(fit_panel["date"].max()),
        }
        path = model_dir(settings) / f"{model_name}.joblib"
        joblib.dump(bundle, path)
        report.artifact_path = str(path)
        logger.info("Saved model bundle to %s", path)
        register_model(database, report, make_active=True)
        append_metrics_history(model_dir(settings) / "metrics_history.csv", report)

    logger.info(
        "Train report: backend=%s n=%d folds=%d IC=%s",
        report.backend,
        report.n_samples,
        report.n_folds,
        f"{mean_ic:.3f}" if mean_ic is not None else "n/a",
    )
    return report
