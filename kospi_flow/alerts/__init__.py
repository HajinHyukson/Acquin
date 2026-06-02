"""Alerting (Phase 5): pluggable notifiers + a rule engine.

The pipeline evaluates alert rules against the database and dispatches any
triggered alerts through a configured notifier (console / file / webhook).
"""

from kospi_flow.alerts.notifier import Alert, get_notifier
from kospi_flow.alerts.rules import evaluate_alerts

__all__ = ["Alert", "get_notifier", "evaluate_alerts"]
