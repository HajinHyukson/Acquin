#!/usr/bin/env python
"""Initialise the database schema from the ORM models.

Thin wrapper around ``python -m kospi_flow.cli init-db``. For shared
deployments prefer the Alembic migrations under ``infra/migrations``.
"""

from kospi_flow.cli import main

if __name__ == "__main__":
    raise SystemExit(main(["init-db"]))
