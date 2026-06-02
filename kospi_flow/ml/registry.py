"""Model registry (Phase 5).

Records each trained model version and its out-of-sample metrics in
``ml_model_registry``, and tracks which version is active for inference.
"""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from kospi_flow.core.db import Database
from kospi_flow.core.logging import get_logger
from kospi_flow.core.models import MlModelRegistry

logger = get_logger(__name__)


def register_model(database: Database, report, make_active: bool = True) -> None:
    """Upsert a registry row from a training report; optionally make it active.

    ``report`` is a ``kospi_flow.ml.train.TrainReport``.
    """
    with database.session() as s:
        if make_active:
            # Deactivate other versions of the same model_name.
            s.execute(
                update(MlModelRegistry)
                .where(MlModelRegistry.model_name == report.model_name)
                .values(is_active=False)
            )
        s.merge(
            MlModelRegistry(
                model_name=report.model_name,
                model_version=report.model_version,
                horizon_days=report.horizon,
                feature_version=report.feature_version,
                backend=report.backend,
                trained_at=getattr(report, "trained_at", None),
                n_samples=report.n_samples,
                mean_ic=report.mean_ic,
                icir=report.icir,
                rmse=report.main_regression.get("rmse"),
                mae=report.main_regression.get("mae"),
                auc=report.classification.get("auc"),
                metrics=report.as_dict(),
                artifact_path=report.artifact_path,
                is_active=make_active,
            )
        )
    logger.info(
        "Registered model %s %s (active=%s)",
        report.model_name,
        report.model_version,
        make_active,
    )


def get_active_model(session: Session, model_name: str) -> MlModelRegistry | None:
    return session.execute(
        select(MlModelRegistry)
        .where(MlModelRegistry.model_name == model_name)
        .where(MlModelRegistry.is_active.is_(True))
        .order_by(MlModelRegistry.model_version.desc())
        .limit(1)
    ).scalar_one_or_none()


def list_models(session: Session) -> list[MlModelRegistry]:
    return list(
        session.execute(
            select(MlModelRegistry).order_by(
                MlModelRegistry.model_name, MlModelRegistry.model_version.desc()
            )
        ).scalars().all()
    )


def set_active(database: Database, model_name: str, model_version: str) -> bool:
    """Mark one version active and the rest inactive. Returns False if absent."""
    with database.session() as s:
        target = s.get(MlModelRegistry, (model_name, model_version))
        if target is None:
            return False
        s.execute(
            update(MlModelRegistry)
            .where(MlModelRegistry.model_name == model_name)
            .values(is_active=False)
        )
        target.is_active = True
    return True
