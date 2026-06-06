"""Retrain runner (context doc §25 Phase D).

Trains every configured horizon under one version stamp, then *syncs* the fresh
bundles + a metrics-history row into the committed ``models/`` dir so they can be
committed and pushed — Railway redeploys with the new bundles baked into the
image. Designed to run on the **KR host** where the real KOSPI data lives
(decided 2026-06-06); this is the human/CI half of the drift-triggered-retrain
loop (the daily pipeline only *recommends* a retrain — see §24.2 / Phase C).

Why sync instead of training straight into ``models/``: training writes bundles
to ``<processed>/models/`` (gitignored), while the committed/baked location is
the repo ``models/`` dir. Copying keeps that separation intact. The metrics
history is *appended* to the durable repo CSV (one row per horizon per retrain),
so it accumulates across runs even if the processed dir is cleared.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from kospi_flow.core.config import Settings, get_settings
from kospi_flow.core.db import Database, get_database
from kospi_flow.core.logging import get_logger
from kospi_flow.ml.train import (
    TrainReport,
    append_metrics_history,
    default_model_version,
    model_dir,
    train_and_evaluate,
)

logger = get_logger(__name__)


@dataclass
class RetrainResult:
    model_version: str
    reports: list[TrainReport] = field(default_factory=list)
    synced: list[str] = field(default_factory=list)
    models_dir: str | None = None


def retrain_all(
    horizons,
    tickers: list[str] | None = None,
    model_version: str | None = None,
    n_splits: int = 3,
    sync: bool = True,
    repo_models_dir: Path | str | None = None,
    database: Database | None = None,
    settings: Settings | None = None,
) -> RetrainResult:
    """Train every horizon under one version, then stage bundles for commit.

    ``sync`` copies each ``<model>.joblib`` from the processed models dir into the
    committed ``models/`` dir and appends this run's metrics rows there. Set
    ``repo_models_dir`` to override that target (tests pass a temp dir so the real
    repo is never touched). ``sync=False`` trains only.
    """
    settings = settings or get_settings()
    database = database or get_database(settings)
    model_version = model_version or default_model_version()
    database.create_all()

    reports: list[TrainReport] = []
    for h in horizons:
        logger.info("Retraining horizon %dd (version %s)", h, model_version)
        reports.append(
            train_and_evaluate(
                database,
                horizon=h,
                tickers=tickers,
                n_splits=n_splits,
                model_version=model_version,
                settings=settings,
            )
        )

    result = RetrainResult(model_version=model_version, reports=reports)
    if not sync:
        return result

    target = Path(repo_models_dir) if repo_models_dir else settings.repo_root / "models"
    target.mkdir(parents=True, exist_ok=True)
    result.models_dir = str(target)
    src_dir = model_dir(settings)
    for report in reports:
        name = f"{report.model_name}.joblib"
        src = src_dir / name
        if src.exists():
            shutil.copy2(src, target / name)
            result.synced.append(name)
        else:  # pragma: no cover - train always writes the bundle when save=True
            logger.warning("Bundle %s not found at %s; skipped sync", name, src)
        # Append to the DURABLE committed history (one row per horizon per run).
        append_metrics_history(target / "metrics_history.csv", report)

    logger.info(
        "Retrained %d horizon(s) %s; synced %d bundle(s) to %s",
        len(reports),
        model_version,
        len(result.synced),
        target,
    )
    return result
