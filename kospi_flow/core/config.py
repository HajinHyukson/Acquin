"""Application configuration.

Settings are read from environment variables (prefix ``KOSPI_``) and an
optional ``.env`` file. See ``.env.example`` for the documented surface.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repository root = three levels up from this file
# (<root>/kospi_flow/core/config.py).
REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Runtime configuration for ingestion, storage, and the database."""

    model_config = SettingsConfigDict(
        env_prefix="KOSPI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Data source -------------------------------------------------------
    #: Provider name resolved by ``kospi_flow.data.providers.get_provider``.
    #: ``sample`` generates deterministic offline data and is the default so
    #: the pipeline runs with no network access or licensed credentials.
    data_source: str = Field(default="sample")

    #: Seconds to pause before each KRX call in the pykrx provider. KRX
    #: rate-limits rapid requests (returns empty responses); a small delay makes
    #: wide multi-year backfills reliable. Raise it if you still see empties.
    pykrx_request_delay: float = Field(default=0.3)

    # --- Database ----------------------------------------------------------
    #: SQLAlchemy URL. Defaults to a local SQLite file for the MVP; point this
    #: at PostgreSQL/TimescaleDB for a shared deployment.
    database_url: str = Field(
        default=f"sqlite:///{(REPO_ROOT / 'data' / 'kospi_flow.db').as_posix()}"
    )
    db_echo: bool = Field(default=False)

    # --- Storage layout ----------------------------------------------------
    raw_data_path: Path = Field(default=REPO_ROOT / "data" / "raw")
    processed_data_path: Path = Field(default=REPO_ROOT / "data" / "processed")

    # --- Time / market -----------------------------------------------------
    #: IANA timezone for market timestamps. Korea time per the context doc.
    timezone: str = Field(default="Asia/Seoul")
    market: str = Field(default="KOSPI")
    #: Benchmark index code used for outperformance labels / market views.
    #: KRX code 1001 = KOSPI. When this index has data it replaces the
    #: cap-weighted proxy computed from the stock universe.
    benchmark_index_code: str = Field(default="1001")

    # --- Alerting (Phase 5) ------------------------------------------------
    #: Notifier channel: none | console | file | webhook.
    alert_channel: str = Field(default="console")
    #: Target file for the ``file`` channel (relative to processed_data_path).
    alert_log_file: str = Field(default="alerts.log")
    #: Webhook URL for the ``webhook`` channel (Slack/Telegram-compatible JSON).
    alert_webhook_url: str | None = Field(default=None)

    # --- Model drift (Phase 5) ---------------------------------------------
    #: PSI thresholds: >= warn -> WARNING, >= alert -> ALERT.
    drift_psi_warn: float = Field(default=0.1)
    drift_psi_alert: float = Field(default=0.25)

    # --- API (Phase 5 deployment hardening) --------------------------------
    #: Comma-separated allowed CORS origins; ``*`` allows all (dev default).
    cors_origins: str = Field(default="*")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def repo_root(self) -> Path:
        return REPO_ROOT

    def ensure_storage_dirs(self) -> None:
        """Create the raw/processed data directories if they do not exist."""
        self.raw_data_path.mkdir(parents=True, exist_ok=True)
        self.processed_data_path.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance."""
    return Settings()
