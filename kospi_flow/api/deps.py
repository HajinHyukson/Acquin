"""FastAPI dependencies.

The :class:`Database` is created once and stored on ``app.state`` by the app
factory; ``get_session`` yields a transactional session per request.
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session

from kospi_flow.core.db import Database


def get_db(request: Request) -> Database:
    return request.app.state.database


def get_session(request: Request) -> Iterator[Session]:
    db: Database = request.app.state.database
    with db.session() as session:
        yield session
