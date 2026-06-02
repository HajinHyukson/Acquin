"""Model factory (context doc §11.4).

Provides a baseline linear model, a gradient-boosting regressor (LightGBM if
installed, else scikit-learn's HistGradientBoosting), a classifier for KOSPI
outperformance, and quantile regressors for P10/P50/P90 bands. Every model is a
``Pipeline`` with median imputation so feature NaNs are handled consistently.
"""

from __future__ import annotations

from sklearn.ensemble import (
    HistGradientBoostingClassifier,
    HistGradientBoostingRegressor,
)
from sklearn.impute import SimpleImputer
from sklearn.linear_model import ElasticNet, LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


def _has_lightgbm() -> bool:
    try:
        import lightgbm  # noqa: F401
    except ImportError:
        return False
    return True


def make_baseline_regressor() -> Pipeline:
    """ElasticNet baseline — interpretable benchmark."""
    return Pipeline(
        steps=[
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            ("model", ElasticNet(alpha=0.001, l1_ratio=0.5, max_iter=5000)),
        ]
    )


def make_regressor() -> Pipeline:
    """Main gradient-boosting return regressor (LightGBM if available)."""
    if _has_lightgbm():
        from lightgbm import LGBMRegressor

        model = LGBMRegressor(
            n_estimators=300, learning_rate=0.05, num_leaves=31, verbose=-1
        )
    else:
        model = HistGradientBoostingRegressor(
            max_iter=300, learning_rate=0.05, max_depth=4
        )
    return Pipeline(
        steps=[("impute", SimpleImputer(strategy="median")), ("model", model)]
    )


def make_classifier() -> Pipeline:
    """Probability of KOSPI outperformance."""
    if _has_lightgbm():
        from lightgbm import LGBMClassifier

        model = LGBMClassifier(
            n_estimators=300, learning_rate=0.05, num_leaves=31, verbose=-1
        )
    else:
        model = HistGradientBoostingClassifier(
            max_iter=300, learning_rate=0.05, max_depth=4
        )
    return Pipeline(
        steps=[("impute", SimpleImputer(strategy="median")), ("model", model)]
    )


def make_quantile_regressor(quantile: float) -> Pipeline:
    """Quantile regressor for prediction bands (P10/P50/P90)."""
    if _has_lightgbm():
        from lightgbm import LGBMRegressor

        model = LGBMRegressor(
            objective="quantile",
            alpha=quantile,
            n_estimators=300,
            learning_rate=0.05,
            verbose=-1,
        )
    else:
        model = HistGradientBoostingRegressor(
            loss="quantile", quantile=quantile, max_iter=300, learning_rate=0.05
        )
    return Pipeline(
        steps=[("impute", SimpleImputer(strategy="median")), ("model", model)]
    )


def backend_name() -> str:
    return "lightgbm" if _has_lightgbm() else "sklearn"
