"""FastAPI backend service (Phase 2+).

The runnable entrypoint lives in ``apps/api/main.py`` and simply imports
``create_app`` from here, keeping all logic inside the importable package so it
is unit-testable.
"""

from kospi_flow.api.app import create_app

__all__ = ["create_app"]
