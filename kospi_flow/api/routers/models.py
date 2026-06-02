"""Model registry + drift endpoints (Phase 5, context doc §13 `/models`)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from kospi_flow.api.deps import get_session
from kospi_flow.api.envelope import envelope, make_metadata, not_found
from kospi_flow.core.models import FactModelDriftDaily, MlModelRegistry
from kospi_flow.ml.registry import list_models

router = APIRouter(prefix="/models", tags=["models"])


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
