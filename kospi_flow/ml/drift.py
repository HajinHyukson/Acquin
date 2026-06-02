"""Feature-drift monitoring via Population Stability Index (Phase 5).

A model's training feature distribution (binned at train time and stored in the
model bundle as ``feature_baseline``) is compared against the live feature
distribution. PSI per feature is summarised to a max/mean and a status, then
persisted to ``fact_model_drift_daily``.

PSI guide: < 0.1 stable, 0.1–0.25 moderate shift, > 0.25 large shift.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from kospi_flow.core.config import Settings, get_settings
from kospi_flow.core.db import Database
from kospi_flow.core.logging import get_logger
from kospi_flow.core.models import FactModelDriftDaily
from kospi_flow.ml.dataset import build_panel

logger = get_logger(__name__)

_EPS = 1e-6


def build_baseline(
    X: pd.DataFrame, feature_cols: list[str], bins: int = 10
) -> dict[str, dict]:
    """Bin each feature on training data; store edges + reference proportions."""
    baseline: dict[str, dict] = {}
    for col in feature_cols:
        vals = X[col].to_numpy(dtype=float)
        vals = vals[~np.isnan(vals)]
        if vals.size < bins:
            continue
        # Quantile edges; dedupe to avoid zero-width bins on constant features.
        edges = np.unique(np.quantile(vals, np.linspace(0, 1, bins + 1)))
        if edges.size < 3:
            continue
        edges[0], edges[-1] = -np.inf, np.inf
        counts, _ = np.histogram(vals, bins=edges)
        props = counts / max(counts.sum(), 1)
        baseline[col] = {"edges": edges.tolist(), "ref_props": props.tolist()}
    return baseline


def feature_psi(values: np.ndarray, edges: list[float], ref_props: list[float]) -> float:
    """PSI of ``values`` against a reference binning."""
    vals = values[~np.isnan(values)]
    if vals.size == 0:
        return 0.0
    counts, _ = np.histogram(vals, bins=np.array(edges, dtype=float))
    cur = counts / max(counts.sum(), 1)
    ref = np.array(ref_props, dtype=float)
    cur = np.clip(cur, _EPS, None)
    ref = np.clip(ref, _EPS, None)
    return float(np.sum((cur - ref) * np.log(cur / ref)))


def status_for(psi: float, settings: Settings) -> str:
    if psi >= settings.drift_psi_alert:
        return "alert"
    if psi >= settings.drift_psi_warn:
        return "warning"
    return "ok"


def compute_drift(
    database: Database,
    bundle: dict,
    window: int = 20,
    settings: Settings | None = None,
    persist: bool = True,
    min_rows: int = 200,
) -> dict:
    """Compare recent features against the bundle baseline; persist a summary.

    ``window`` = number of most-recent trading dates of live features to score.
    PSI is unreliable on small samples, so if fewer than ``min_rows`` feature
    rows are available the status is ``low_sample`` and no drift alert is raised
    (a wide production universe easily exceeds this; the demo universe will not).
    Returns a summary dict; if no baseline is present, returns status 'unknown'.
    """
    settings = settings or get_settings()
    baseline = bundle.get("feature_baseline") or {}
    feature_cols = bundle["feature_cols"]
    model_name = bundle["model_name"]

    if not baseline:
        return {"model_name": model_name, "status": "unknown", "detail": {}}

    with database.session() as s:
        panel, _cols = build_panel(s, horizon=1)
        if panel.empty:
            return {"model_name": model_name, "status": "unknown", "n_rows": 0}
        recent_dates = sorted(panel["date"].unique())[-window:]
        recent = panel[panel["date"].isin(recent_dates)]

        per_feature: dict[str, float] = {}
        for col in feature_cols:
            if col not in baseline or col not in recent.columns:
                continue
            psi = feature_psi(
                recent[col].to_numpy(dtype=float),
                baseline[col]["edges"],
                baseline[col]["ref_props"],
            )
            per_feature[col] = psi

        if not per_feature:
            return {"model_name": model_name, "status": "unknown", "n_rows": len(recent)}

        max_psi = max(per_feature.values())
        mean_psi = float(np.mean(list(per_feature.values())))
        # Guard against PSI noise on small samples.
        if len(recent) < min_rows:
            status = "low_sample"
        else:
            status = status_for(max_psi, settings)
        run_date = max(recent_dates)

        if persist:
            s.merge(
                FactModelDriftDaily(
                    date=run_date,
                    model_name=model_name,
                    model_version=bundle.get("model_version"),
                    max_psi=max_psi,
                    mean_psi=mean_psi,
                    status=status,
                    n_rows=int(len(recent)),
                    detail=per_feature,
                )
            )

    logger.info(
        "Drift for %s: status=%s max_psi=%.3f", model_name, status, max_psi
    )
    return {
        "model_name": model_name,
        "date": run_date.isoformat(),
        "status": status,
        "max_psi": max_psi,
        "mean_psi": mean_psi,
        "n_rows": int(len(recent)),
        "detail": per_feature,
    }
