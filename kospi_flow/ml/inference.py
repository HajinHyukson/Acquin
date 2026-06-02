"""Daily inference: load a model bundle, predict, store to fact_ml_prediction_daily.

Predicted price is derived from the latest close and the predicted log return:
``predicted_price = close * exp(predicted_return)``. Quantile models give the
P10/P50/P90 return band; the classifier gives probability of KOSPI outperformance.
"""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np

from kospi_flow.core.config import Settings, get_settings
from kospi_flow.core.db import Database
from kospi_flow.core.logging import get_logger
from kospi_flow.core.models import FactMlPredictionDaily
from kospi_flow.ml.dataset import latest_feature_rows
from kospi_flow.ml.train import model_dir

logger = get_logger(__name__)


def load_bundle(model_name: str, settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    path = Path(model_dir(settings)) / f"{model_name}.joblib"
    if not path.exists():
        raise FileNotFoundError(
            f"Model '{model_name}' not found at {path}. Train it first "
            f"(`python -m kospi_flow.cli train`)."
        )
    return joblib.load(path)


def predict_and_store(
    database: Database,
    model_name: str,
    tickers: list[str] | None = None,
    settings: Settings | None = None,
) -> int:
    """Generate predictions for the latest available date and upsert them."""
    settings = settings or get_settings()
    bundle = load_bundle(model_name, settings)
    feature_cols = bundle["feature_cols"]
    horizon = bundle["horizon"]

    with database.session() as s:
        latest, _cols = latest_feature_rows(s, tickers)
        if latest.empty:
            logger.warning("No feature rows for inference.")
            return 0
        # Align to the columns the model was trained on.
        for c in feature_cols:
            if c not in latest.columns:
                latest[c] = np.nan
        X = latest[feature_cols]

        pred_ret = bundle["regressor"].predict(X)
        prob = bundle["classifier"].predict_proba(X)[:, 1]
        q = {name: m.predict(X) for name, m in bundle["quantiles"].items()}

        count = 0
        for i, row in latest.reset_index(drop=True).iterrows():
            close = row.get("close_price")
            r = float(pred_ret[i])
            price = (
                float(close * np.exp(r)) if close and not np.isnan(close) else None
            )
            s.merge(
                FactMlPredictionDaily(
                    date=row["date"],
                    ticker=row["ticker"],
                    horizon_days=horizon,
                    model_name=model_name,
                    predicted_return=r,
                    predicted_price=price,
                    predicted_return_p10=float(q[0.1][i]),
                    predicted_return_p50=float(q[0.5][i]),
                    predicted_return_p90=float(q[0.9][i]),
                    prob_outperform_kospi=float(prob[i]),
                    model_version=bundle["model_version"],
                    feature_version=bundle["feature_version"],
                )
            )
            count += 1
        logger.info("Stored %d predictions for model '%s'", count, model_name)
        return count
