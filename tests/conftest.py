"""Shared pytest fixtures."""

from __future__ import annotations

from datetime import date

import pytest

from kospi_flow.core import config
from kospi_flow.core.db import Database

# Make the whole suite hermetic against a developer's local ``.env``. Without
# this, a real ``.env`` (e.g. ``KOSPI_DATA_SOURCE=pykrx`` set for a live
# backfill) leaks into tests — flipping config defaults and pointing the
# pipeline at a network provider. Applied at conftest import time so it takes
# effect before any (even module-scoped) fixture constructs a Settings object.
config.Settings.model_config["env_file"] = None
config.get_settings.cache_clear()


@pytest.fixture
def db() -> Database:
    """In-memory SQLite database with the schema created."""
    database = Database("sqlite:///:memory:")
    database.create_all()
    return database


@pytest.fixture
def date_range() -> tuple[date, date]:
    """A fixed multi-month range (avoids any reliance on the wall clock)."""
    return date(2021, 1, 4), date(2021, 4, 30)
