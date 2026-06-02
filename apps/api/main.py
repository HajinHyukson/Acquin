"""Runnable FastAPI entrypoint.

    uvicorn apps.api.main:app --reload

All application logic lives in the importable ``kospi_flow.api`` package; this
module just exposes the ASGI ``app`` object.
"""

from kospi_flow.api import create_app

app = create_app()
