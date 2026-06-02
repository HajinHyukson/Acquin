"""Configuration defaults and env-var overrides."""

from __future__ import annotations

from kospi_flow.core.config import Settings


def test_defaults(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("KOSPI_DATABASE_URL", raising=False)
    s = Settings()
    assert s.data_source == "sample"
    assert s.timezone == "Asia/Seoul"
    assert s.market == "KOSPI"
    assert "sqlite" in s.database_url


def test_env_override(monkeypatch):
    monkeypatch.setenv("KOSPI_DATA_SOURCE", "pykrx")
    monkeypatch.setenv("KOSPI_TIMEZONE", "UTC")
    s = Settings()
    assert s.data_source == "pykrx"
    assert s.timezone == "UTC"


def test_database_url_falls_back_to_platform_env(monkeypatch):
    # Railway/Render/Heroku inject DATABASE_URL; we adopt it when KOSPI_DATABASE_URL is unset.
    monkeypatch.delenv("KOSPI_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@h:5432/db")
    assert Settings().database_url == "postgres://u:p@h:5432/db"


def test_kospi_database_url_overrides_platform(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://platform/db")
    monkeypatch.setenv("KOSPI_DATABASE_URL", "sqlite:///./x.db")
    assert Settings().database_url == "sqlite:///./x.db"
