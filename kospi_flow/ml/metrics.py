"""Evaluation metrics (context doc §11.6).

Includes return-error metrics, directional accuracy, classification AUC, and the
ranking metrics that matter most for stock selection: Daily Spearman IC and ICIR.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.metrics import roc_auc_score


def regression_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    mask = ~(np.isnan(y_true) | np.isnan(y_pred))
    y_true, y_pred = y_true[mask], y_pred[mask]
    if len(y_true) == 0:
        return {"n": 0, "mae": None, "rmse": None, "directional_accuracy": None}
    err = y_pred - y_true
    return {
        "n": int(len(y_true)),
        "mae": float(np.mean(np.abs(err))),
        "rmse": float(np.sqrt(np.mean(err**2))),
        "directional_accuracy": float(np.mean(np.sign(y_pred) == np.sign(y_true))),
    }


def classification_metrics(y_true: np.ndarray, y_prob: np.ndarray) -> dict:
    mask = ~(np.isnan(y_true) | np.isnan(y_prob))
    y_true, y_prob = y_true[mask], y_prob[mask]
    auc = None
    if len(np.unique(y_true)) == 2:
        auc = float(roc_auc_score(y_true, y_prob))
    return {"n": int(len(y_true)), "auc": auc}


def daily_ic(
    dates: pd.Series, y_true: np.ndarray, y_pred: np.ndarray
) -> tuple[float | None, float | None, list[float]]:
    """Mean daily Spearman IC and ICIR (mean/std of daily IC).

    Returns (mean_ic, icir, per_day_ic). Days with < 3 names or constant input
    are skipped.
    """
    df = pd.DataFrame({"date": dates.to_numpy(), "yt": y_true, "yp": y_pred}).dropna()
    ics: list[float] = []
    for _, g in df.groupby("date"):
        if len(g) >= 3 and g["yt"].std() > 0 and g["yp"].std() > 0:
            ic = stats.spearmanr(g["yp"], g["yt"]).statistic
            if not np.isnan(ic):
                ics.append(float(ic))
    if not ics:
        return None, None, []
    mean_ic = float(np.mean(ics))
    icir = float(mean_ic / np.std(ics)) if np.std(ics) > 0 else None
    return mean_ic, icir, ics
