"""Walk-forward backtest: store per-stock historical out-of-sample predictions.

Replays the model through history with the same leak-safe walk-forward folds
used for training (train strictly before test, embargo >= horizon), but keeps
the per-(date, ticker) test-block predictions instead of only the aggregate
metrics. Each stored row answers: "standing at date t, knowing only data up to
t, what did the model predict for t+h?" — realized outcomes are joined from
prices at query time by the ``/stocks/{ticker}/prediction-accuracy`` endpoint.

Rows live in ``fact_ml_prediction_daily`` (no schema change — its PK already
includes ``model_name``) under a ``wf::``-prefixed model name so live inference
rows, external-model rows, and backtest rows coexist in one table and the live
endpoints (projection, top-picks) can exclude them with one filter.

Footprint note: one horizon over the full 5y/948-ticker panel stores on the
order of the OOS panel size (hundreds of thousands of rows). Run it for the
horizons the UI features (5d/20d) rather than all five if DB size matters.
"""

from __future__ import annotations

from datetime import date

import numpy as np
from sqlalchemy import delete, insert

from kospi_flow.core.config import Settings, get_settings
from kospi_flow.core.db import Database
from kospi_flow.core.logging import get_logger
from kospi_flow.core.models import FactMlPredictionDaily
from kospi_flow.ml.dataset import FEATURE_VERSION, build_dataset
from kospi_flow.ml.models import (
    make_classifier,
    make_quantile_regressor,
    make_regressor,
)
from kospi_flow.ml.validation import split_panel, walk_forward_splits

logger = get_logger(__name__)

#: Prefix marking historical walk-forward rows in ``fact_ml_prediction_daily``.
#: Live endpoints exclude ``wf::%``; the accuracy endpoint includes them.
BACKTEST_PREFIX = "wf::"

_INSERT_CHUNK = 5000


def backtest_model_name(model_name: str) -> str:
    return f"{BACKTEST_PREFIX}{model_name}"


def walk_forward_backtest(
    database: Database,
    horizon: int = 5,
    tickers: list[str] | None = None,
    n_splits: int = 8,
    min_train: int = 126,
    model_name: str | None = None,
    model_version: str | None = None,
    settings: Settings | None = None,
) -> int:
    """Generate + store walk-forward OOS predictions; returns rows stored.

    Re-running replaces the previous backtest for the same model/horizon (the
    folds are deterministic, so partial appends would only duplicate). More
    ``n_splits`` = more of history covered out-of-sample, at more training cost.
    """
    settings = settings or get_settings()
    base_name = model_name or f"gbm_return_{horizon}d"
    stored_name = backtest_model_name(base_name)
    model_version = model_version or f"wf{date.today():%Y%m%d}"

    with database.session() as s:
        panel, feature_cols = build_dataset(s, horizon, tickers)
    if panel.empty or not feature_cols:
        logger.warning("No data to backtest; ingest data first.")
        return 0

    folds = walk_forward_splits(
        panel["date"],
        n_splits=n_splits,
        embargo=horizon,
        min_train=min_train,
        train_window=settings.train_window_days,
    )
    if not folds:
        logger.warning("Not enough history for walk-forward folds.")
        return 0

    rows: list[dict] = []
    for i, fold in enumerate(folds):
        train, test = split_panel(panel, fold)
        if train.empty or test.empty:
            continue
        Xtr, ytr = train[feature_cols], train["y_reg"].to_numpy()
        reg = make_regressor().fit(Xtr, ytr)
        clf = make_classifier().fit(Xtr, train["y_cls"].to_numpy())
        quants = {
            q: make_quantile_regressor(q).fit(Xtr, ytr) for q in (0.1, 0.5, 0.9)
        }

        test = test.reset_index(drop=True)
        Xte = test[feature_cols]
        pred = reg.predict(Xte)
        prob = clf.predict_proba(Xte)[:, 1]
        qp = {q: m.predict(Xte) for q, m in quants.items()}

        closes = test["close_price"].to_numpy(dtype=float)
        with np.errstate(invalid="ignore"):
            prices = np.where(np.isnan(closes), np.nan, closes * np.exp(pred))
        for j in range(len(test)):
            rows.append(
                {
                    "date": test.at[j, "date"],
                    "ticker": test.at[j, "ticker"],
                    "horizon_days": horizon,
                    "model_name": stored_name,
                    "predicted_return": float(pred[j]),
                    "predicted_price": None if np.isnan(prices[j]) else float(prices[j]),
                    "predicted_return_p10": float(qp[0.1][j]),
                    "predicted_return_p50": float(qp[0.5][j]),
                    "predicted_return_p90": float(qp[0.9][j]),
                    "prob_outperform_kospi": float(prob[j]),
                    "model_version": model_version,
                    "feature_version": FEATURE_VERSION,
                }
            )
        logger.info(
            "Backtest fold %d/%d: train=%d test=%d", i + 1, len(folds), len(train), len(test)
        )

    with database.session() as s:
        s.execute(
            delete(FactMlPredictionDaily)
            .where(FactMlPredictionDaily.model_name == stored_name)
            .where(FactMlPredictionDaily.horizon_days == horizon)
        )
        for start in range(0, len(rows), _INSERT_CHUNK):
            s.execute(insert(FactMlPredictionDaily), rows[start : start + _INSERT_CHUNK])
    logger.info("Stored %d backtest predictions as '%s'", len(rows), stored_name)
    return len(rows)
