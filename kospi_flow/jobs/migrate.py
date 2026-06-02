"""Copy all data from one database to another (e.g. local SQLite → Postgres).

Used to push a locally-built dataset up to the hosted production database. Tables
are copied in FK-dependency order and inserted in batches. The destination must
be empty (fresh) — this does not upsert or dedupe.

For very large tables `pgloader` is faster, but this keeps the migration
in-project and works across any SQLAlchemy-supported dialect.
"""

from __future__ import annotations

from sqlalchemy import select

from kospi_flow.core.db import Database
from kospi_flow.core.logging import get_logger
from kospi_flow.core.models import Base

logger = get_logger(__name__)


def copy_database(
    source_url: str, dest_url: str, batch: int = 5000, create: bool = True
) -> dict[str, int]:
    """Copy every ORM table from ``source_url`` to ``dest_url``.

    Returns a per-table row count. Creates the schema on the destination first
    (unless ``create=False``).
    """
    src = Database(source_url)
    dst = Database(dest_url)
    if create:
        dst.create_all()

    counts: dict[str, int] = {}
    # sorted_tables orders parents before children (dim_stock before facts).
    with src.engine.connect() as sconn, dst.engine.begin() as dconn:
        for table in Base.metadata.sorted_tables:
            result = sconn.execution_options(stream_results=True).execute(
                select(table)
            )
            inserted = 0
            buf: list[dict] = []
            for row in result.mappings():
                buf.append(dict(row))
                if len(buf) >= batch:
                    dconn.execute(table.insert(), buf)
                    inserted += len(buf)
                    buf = []
            if buf:
                dconn.execute(table.insert(), buf)
                inserted += len(buf)
            counts[table.name] = inserted
            logger.info("Copied %s: %d rows", table.name, inserted)

    logger.info("Copy complete: %s", counts)
    return counts
