"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from kospi_flow.api.envelope import ApiError
from kospi_flow.api.routers import (
    analytics,
    market,
    metadata,
    models,
    projection,
    screeners,
    status,
    stocks,
    watchlists,
)
from kospi_flow.core.config import Settings, get_settings
from kospi_flow.core.db import Database, get_database


def create_app(
    settings: Settings | None = None, database: Database | None = None
) -> FastAPI:
    """Build the FastAPI app. A custom ``database`` can be injected for tests."""
    settings = settings or get_settings()
    app = FastAPI(
        title="KOSPI Investor Flow Intelligence Platform",
        version="0.3.0",
        description="Investor-flow (개인/기관/외국인 순매수) tracking, screeners, "
        "analytics, ML projections, watchlists, and model monitoring for KOSPI.",
    )
    app.state.settings = settings
    app.state.database = database or get_database(settings)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(ApiError)
    async def _api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.to_body())

    app.include_router(metadata.router)
    app.include_router(stocks.router)
    app.include_router(market.router)
    app.include_router(screeners.router)
    app.include_router(analytics.router)
    app.include_router(projection.router)
    app.include_router(status.router)
    app.include_router(watchlists.router)
    app.include_router(models.router)
    return app
