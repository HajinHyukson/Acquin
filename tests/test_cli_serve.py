"""Port resolution for `serve` (tolerates un-expanded $PORT from platforms)."""

from __future__ import annotations

from kospi_flow.cli import resolve_port


def test_literal_port(monkeypatch):
    monkeypatch.delenv("PORT", raising=False)
    assert resolve_port("8080") == 8080


def test_none_uses_env(monkeypatch):
    monkeypatch.setenv("PORT", "7000")
    assert resolve_port(None) == 7000


def test_unexpanded_placeholder_falls_back_to_env(monkeypatch):
    # Railway/Heroku sometimes pass "$PORT" literally; the PORT env still exists.
    monkeypatch.setenv("PORT", "9000")
    assert resolve_port("$PORT") == 9000
    assert resolve_port("${PORT}") == 9000


def test_no_port_anywhere_defaults_8000(monkeypatch):
    monkeypatch.delenv("PORT", raising=False)
    assert resolve_port(None) == 8000
    assert resolve_port("$PORT") == 8000
