"""Data-status / data-quality endpoint (context doc §13.1 `/data-status`)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from kospi_flow.api.deps import get_db
from kospi_flow.api.envelope import envelope, make_metadata
from kospi_flow.core.db import Database
from kospi_flow.data.validation import DataValidator

router = APIRouter(tags=["status"])


@router.get("/data-status")
def data_status(db: Database = Depends(get_db)) -> dict:
    """Row counts plus the latest validation report (errors/warnings)."""
    report = DataValidator(db).validate()
    data = {
        "ok": report.ok,
        "counts": report.counts,
        "errors": [i.__dict__ for i in report.errors],
        "warnings": [i.__dict__ for i in report.warnings][:50],
    }
    return envelope(data, make_metadata())
