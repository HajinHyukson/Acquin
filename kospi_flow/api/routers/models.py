"""Model registry, drift, and external-prediction ingest endpoints.

The ingest endpoint is the write side of the external-model socket
(docs/EXTERNAL_MODELS.md): a separately developed model (e.g. an investor-
sentiment model) pushes its predictions here and they flow through the same
storage, projection, top-picks, and accuracy machinery as the internal models.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from kospi_flow.api.deps import get_session
from kospi_flow.api.envelope import ApiError, envelope, make_metadata, not_found
from kospi_flow.api.schemas import ExternalPredictionsPayload
from kospi_flow.core.models import (
    DimStock,
    FactMlPredictionDaily,
    FactModelDriftDaily,
    MlModelRegistry,
)
from kospi_flow.ml.backtest import BACKTEST_PREFIX
from kospi_flow.ml.registry import list_models

router = APIRouter(prefix="/models", tags=["models"])

#: Prefixes external models may not use: ``gbm_`` is the internal trainer's
#: namespace; ``wf::`` marks walk-forward backtest rows.
RESERVED_PREFIXES = ("gbm_", BACKTEST_PREFIX)


def require_ingest_key(
    request: Request, x_api_key: str | None = Header(default=None)
) -> None:
    """Guard for prediction writes. Disabled entirely until a key is configured."""
    settings = request.app.state.settings
    if not settings.ingest_api_key:
        raise ApiError(
            403,
            "INGEST_DISABLED",
            "External prediction ingest is disabled. Set KOSPI_INGEST_API_KEY "
            "on the API service to enable it.",
        )
    if x_api_key != settings.ingest_api_key:
        raise ApiError(401, "INVALID_API_KEY", "Missing or invalid X-API-Key header.")


@router.get("")
def get_models(session: Session = Depends(get_session)) -> dict:
    """Registered models and their out-of-sample metrics."""
    rows = list_models(session)
    data = [
        {
            "model_name": r.model_name,
            "model_version": r.model_version,
            "horizon_days": r.horizon_days,
            "backend": r.backend,
            "is_active": r.is_active,
            "n_samples": r.n_samples,
            "mean_ic": r.mean_ic,
            "icir": r.icir,
            "rmse": r.rmse,
            "mae": r.mae,
            "auc": r.auc,
            "trained_at": r.trained_at,
            "feature_version": r.feature_version,
        }
        for r in rows
    ]
    return envelope(data, make_metadata(extra_count=len(data)))


@router.post("/{model_name}/predictions", dependencies=[Depends(require_ingest_key)])
def ingest_predictions(
    model_name: str,
    payload: ExternalPredictionsPayload,
    session: Session = Depends(get_session),
) -> dict:
    """Upsert predictions from an external model (the model socket's write side).

    Rows land in ``fact_ml_prediction_daily`` keyed by ``model_name``, so they
    appear on stock pages (projection ``models`` groups), in ``/market/top-picks``
    via ``?model=``, and — once outcomes mature — in the prediction-accuracy
    panel. Unknown tickers are skipped and reported, not rejected.
    """
    if any(model_name.startswith(p) for p in RESERVED_PREFIXES):
        raise ApiError(
            422,
            "RESERVED_MODEL_NAME",
            f"Model names starting with {RESERVED_PREFIXES} are reserved for "
            "the internal pipeline.",
            {"model_name": model_name},
        )

    known = {
        t for (t,) in session.execute(select(DimStock.ticker)).all()
    }
    stored = 0
    skipped: set[str] = set()
    latest = None
    for row in payload.predictions:
        if row.ticker not in known:
            skipped.add(row.ticker)
            continue
        session.merge(
            FactMlPredictionDaily(
                date=row.date,
                ticker=row.ticker,
                horizon_days=row.horizon_days,
                model_name=model_name,
                predicted_return=row.predicted_return,
                predicted_price=row.predicted_price,
                predicted_return_p10=row.predicted_return_p10,
                predicted_return_p50=row.predicted_return_p50,
                predicted_return_p90=row.predicted_return_p90,
                prob_outperform_kospi=row.prob_outperform_kospi,
                model_version=payload.model_version,
                feature_version=payload.feature_version,
            )
        )
        stored += 1
        latest = row.date if latest is None or row.date > latest else latest

    # Register the external model so /models lists it next to internal ones.
    if stored and session.get(MlModelRegistry, (model_name, payload.model_version)) is None:
        session.add(
            MlModelRegistry(
                model_name=model_name,
                model_version=payload.model_version,
                feature_version=payload.feature_version,
                backend="external",
                n_samples=stored,
                is_active=True,
            )
        )

    return envelope(
        {
            "model_name": model_name,
            "model_version": payload.model_version,
            "stored": stored,
            "skipped_unknown_tickers": sorted(skipped),
        },
        make_metadata(latest_data_date=latest, source="external"),
    )


@router.get("/{model_name}/drift")
def model_drift(model_name: str, session: Session = Depends(get_session)) -> dict:
    """Latest persisted drift summary for a model."""
    if not _exists(session, model_name):
        raise not_found(f"Unknown model '{model_name}'.", model_name=model_name)
    row = session.execute(
        select(FactModelDriftDaily)
        .where(FactModelDriftDaily.model_name == model_name)
        .order_by(FactModelDriftDaily.date.desc())
        .limit(1)
    ).scalar_one_or_none()
    if row is None:
        raise not_found(
            "No drift record yet for this model. Run monitoring first.",
            model_name=model_name,
        )
    data = {
        "model_name": row.model_name,
        "model_version": row.model_version,
        "date": row.date.isoformat(),
        "status": row.status,
        "max_psi": row.max_psi,
        "mean_psi": row.mean_psi,
        "n_rows": row.n_rows,
        "detail": row.detail,
    }
    return envelope(data, make_metadata(latest_data_date=row.date))


def _exists(session: Session, model_name: str) -> bool:
    return session.execute(
        select(MlModelRegistry.model_name)
        .where(MlModelRegistry.model_name == model_name)
        .limit(1)
    ).first() is not None
