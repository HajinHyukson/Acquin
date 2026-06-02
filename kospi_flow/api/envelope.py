"""Response/error envelope helpers (context doc §12.2).

Every successful response is wrapped as ``{"data": ..., "metadata": {...}}`` and
every error as ``{"error": {...}}``. ``generated_at`` uses Korea time.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from kospi_flow.core.config import get_settings


def _now_kst_iso() -> str:
    tz = ZoneInfo(get_settings().timezone)
    return datetime.now(tz).replace(microsecond=0).isoformat()


def make_metadata(
    source: str | None = None,
    freshness_state: str | None = None,
    latest_data_date: date | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Build the metadata block attached to every successful response."""
    meta: dict[str, Any] = {
        "source": source,
        "freshness_state": freshness_state,
        "latest_data_date": latest_data_date.isoformat() if latest_data_date else None,
        "generated_at": _now_kst_iso(),
    }
    meta.update(extra)
    return meta


def envelope(data: Any, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Wrap ``data`` with a metadata block."""
    return {"data": data, "metadata": metadata or make_metadata()}


class ApiError(HTTPException):
    """HTTPException that renders the documented error envelope."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=message)
        self.code = code
        self.message = message
        self.details = details or {}

    def to_body(self) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }


def not_found(message: str, **details: Any) -> ApiError:
    return ApiError(404, "DATA_NOT_AVAILABLE", message, details or None)
