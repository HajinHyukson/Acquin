"""Database engine and session management."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from kospi_flow.core.config import Settings, get_settings
from kospi_flow.core.models import Base


def normalize_db_url(url: str) -> str:
    """Normalize platform-provided Postgres DSNs to the psycopg3 dialect.

    Hosts like Render/Railway/Heroku hand out ``postgres://`` or
    ``postgresql://`` URLs, which SQLAlchemy maps to the (often missing)
    psycopg2 driver. We use psycopg3, so rewrite them to
    ``postgresql+psycopg://``. SQLite and already-qualified URLs pass through.
    """
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


class Database:
    """Thin wrapper around a SQLAlchemy engine + session factory."""

    def __init__(self, url: str, echo: bool = False) -> None:
        url = normalize_db_url(url)
        self.url = url
        connect_args = {}
        # SQLite needs this to be usable across threads (e.g. API workers).
        if url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        self.engine: Engine = create_engine(
            url, echo=echo, future=True, connect_args=connect_args
        )
        self._session_factory = sessionmaker(
            bind=self.engine, expire_on_commit=False, future=True
        )

    def create_all(self) -> None:
        """Create every table from the ORM metadata.

        Convenience path for local/MVP use. For shared deployments prefer the
        Alembic migrations under ``infra/migrations``.
        """
        Base.metadata.create_all(self.engine)

    def drop_all(self) -> None:
        """Drop every table. Used by tests."""
        Base.metadata.drop_all(self.engine)

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Transactional session scope: commit on success, rollback on error."""
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


def get_database(settings: Settings | None = None) -> Database:
    """Build a :class:`Database` from settings (defaults to ``get_settings``)."""
    settings = settings or get_settings()
    return Database(settings.database_url, echo=settings.db_echo)
