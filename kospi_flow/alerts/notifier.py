"""Notifier abstraction and built-in channels (Phase 5).

Channels are pluggable so email/Kakao/Telegram/Slack can be added later by
implementing :class:`Notifier`. The default is the console notifier; ``webhook``
posts a JSON payload compatible with Slack/Telegram-style incoming webhooks.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from kospi_flow.core.config import Settings, get_settings
from kospi_flow.core.logging import get_logger

logger = get_logger(__name__)

# Severity ordering for filtering/sorting.
SEVERITY_ORDER = {"info": 0, "warning": 1, "critical": 2}


@dataclass
class Alert:
    """A single alert to dispatch."""

    code: str
    severity: str  # info | warning | critical
    message: str
    context: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "context": self.context,
        }

    def format_text(self) -> str:
        prefix = {"info": "ℹ️", "warning": "⚠️", "critical": "🚨"}.get(
            self.severity, ""
        )
        return f"{prefix} [{self.severity.upper()}] {self.code}: {self.message}"


class Notifier(ABC):
    """Dispatch alerts somewhere. Implementations must not raise on send."""

    name = "base"

    @abstractmethod
    def send(self, alert: Alert) -> bool:
        """Deliver one alert; return True on success."""

    def send_many(self, alerts: list[Alert]) -> int:
        """Deliver several alerts; return the count successfully sent."""
        return sum(1 for a in alerts if self.send(a))


class ConsoleNotifier(Notifier):
    name = "console"

    def send(self, alert: Alert) -> bool:
        log = logger.warning if alert.severity != "info" else logger.info
        log("ALERT %s", alert.format_text())
        return True


class NullNotifier(Notifier):
    """Drops alerts (channel = none)."""

    name = "none"

    def send(self, alert: Alert) -> bool:
        return True


class FileNotifier(Notifier):
    name = "file"

    def __init__(self, path: Path) -> None:
        self.path = path

    def send(self, alert: Alert) -> bool:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(alert.as_dict(), ensure_ascii=False) + "\n")
            return True
        except Exception as exc:  # noqa: BLE001 - notifier must not raise
            logger.error("FileNotifier failed: %s", exc)
            return False


class WebhookNotifier(Notifier):
    name = "webhook"

    def __init__(self, url: str) -> None:
        self.url = url

    def send(self, alert: Alert) -> bool:
        try:
            import httpx

            payload = {"text": alert.format_text(), "alert": alert.as_dict()}
            resp = httpx.post(self.url, json=payload, timeout=10.0)
            return resp.status_code < 400
        except Exception as exc:  # noqa: BLE001 - notifier must not raise
            logger.error("WebhookNotifier failed: %s", exc)
            return False


def get_notifier(settings: Settings | None = None) -> Notifier:
    """Build the notifier for the configured ``alert_channel``."""
    settings = settings or get_settings()
    channel = (settings.alert_channel or "none").lower()
    if channel == "none":
        return NullNotifier()
    if channel == "console":
        return ConsoleNotifier()
    if channel == "file":
        return FileNotifier(settings.processed_data_path / settings.alert_log_file)
    if channel == "webhook":
        if not settings.alert_webhook_url:
            logger.warning("alert_channel=webhook but no alert_webhook_url; using console")
            return ConsoleNotifier()
        return WebhookNotifier(settings.alert_webhook_url)
    logger.warning("Unknown alert_channel '%s'; using console", channel)
    return ConsoleNotifier()
