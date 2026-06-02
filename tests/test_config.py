"""Configuration defaults and env-var overrides."""

from __future__ import annotations

from kospi_flow.core.config import Settings


def test_defaults():
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
