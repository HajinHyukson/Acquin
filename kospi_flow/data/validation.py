"""Data validation utilities.

Checks the core tables for the problems called out in the acceptance criteria:
missing rows, duplicate rows, date-coverage gaps, and data freshness. Results
are returned as structured :class:`ValidationIssue` records and also logged, so
nothing fails silently (context doc, sections 6.3 and 19.1).

The price table's distinct trading dates per ticker are used as the reference
calendar: investor-flow and foreign-holding coverage are checked against the
dates for which we have a price, which avoids depending on an external KRX
holiday calendar in the MVP.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import func, select

from kospi_flow.core.db import Database
from kospi_flow.core.enums import MVP_INVESTOR_GROUPS, FreshnessState
from kospi_flow.core.logging import get_logger
from kospi_flow.core.models import (
    DimStock,
    FactForeignHoldingDaily,
    FactInvestorFlowDaily,
    FactPriceDaily,
)

logger = get_logger(__name__)

SEVERITY_ERROR = "ERROR"
SEVERITY_WARNING = "WARNING"


@dataclass
class ValidationIssue:
    """A single validation finding."""

    check: str
    severity: str
    message: str
    ticker: str | None = None


@dataclass
class ValidationReport:
    """Aggregated validation results."""

    issues: list[ValidationIssue] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    def add(
        self, check: str, severity: str, message: str, ticker: str | None = None
    ) -> None:
        self.issues.append(ValidationIssue(check, severity, message, ticker))

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == SEVERITY_ERROR]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == SEVERITY_WARNING]

    @property
    def ok(self) -> bool:
        return not self.errors

    def summary(self) -> str:
        return (
            f"counts={self.counts} errors={len(self.errors)} "
            f"warnings={len(self.warnings)}"
        )


_VALID_FRESHNESS = {s.value for s in FreshnessState}


class DataValidator:
    """Runs validation checks against the database."""

    def __init__(self, database: Database) -> None:
        self.db = database

    def validate(self, tickers: list[str] | None = None) -> ValidationReport:
        report = ValidationReport()
        with self.db.session() as s:
            self._count_rows(s, report)
            self._check_row_presence(s, report)
            self._check_duplicates(s, report)
            self._check_freshness(s, report)
            self._check_coverage(s, report, tickers)
        logger.info("Validation: %s", report.summary())
        for issue in report.errors:
            logger.error("[%s] %s", issue.check, issue.message)
        for issue in report.warnings:
            logger.warning("[%s] %s", issue.check, issue.message)
        return report

    # -- individual checks --------------------------------------------------
    def _count_rows(self, s, report: ValidationReport) -> None:
        report.counts["dim_stock"] = (
            s.scalar(select(func.count()).select_from(DimStock)) or 0
        )
        report.counts["fact_price_daily"] = (
            s.scalar(select(func.count()).select_from(FactPriceDaily)) or 0
        )
        report.counts["fact_investor_flow_daily"] = (
            s.scalar(select(func.count()).select_from(FactInvestorFlowDaily)) or 0
        )
        report.counts["fact_foreign_holding_daily"] = (
            s.scalar(select(func.count()).select_from(FactForeignHoldingDaily)) or 0
        )

    def _check_row_presence(self, s, report: ValidationReport) -> None:
        """Every table that should hold data is non-empty."""
        for table_name, count in report.counts.items():
            if table_name == "fact_foreign_holding_daily":
                # Optional depending on provider; warn rather than error.
                if count == 0:
                    report.add(
                        "row_presence",
                        SEVERITY_WARNING,
                        f"{table_name} is empty (provider may not supply it)",
                    )
                continue
            if count == 0:
                report.add(
                    "row_presence",
                    SEVERITY_ERROR,
                    f"{table_name} has no rows",
                )

    def _check_duplicates(self, s, report: ValidationReport) -> None:
        """Primary-key uniqueness sanity check (defence-in-depth vs. the PK)."""
        checks = [
            (
                "fact_price_daily",
                FactPriceDaily,
                [FactPriceDaily.date, FactPriceDaily.ticker],
            ),
            (
                "fact_investor_flow_daily",
                FactInvestorFlowDaily,
                [
                    FactInvestorFlowDaily.date,
                    FactInvestorFlowDaily.ticker,
                    FactInvestorFlowDaily.investor_group,
                ],
            ),
            (
                "fact_foreign_holding_daily",
                FactForeignHoldingDaily,
                [FactForeignHoldingDaily.date, FactForeignHoldingDaily.ticker],
            ),
        ]
        for name, model, key_cols in checks:
            dup_count = s.scalar(
                select(func.count()).select_from(
                    select(*key_cols)
                    .group_by(*key_cols)
                    .having(func.count() > 1)
                    .subquery()
                )
            )
            if dup_count:
                report.add(
                    "duplicates",
                    SEVERITY_ERROR,
                    f"{name} has {dup_count} duplicated key group(s)",
                )

    def _check_freshness(self, s, report: ValidationReport) -> None:
        """Freshness state must be present and a known value on every fact row."""
        for name, model in [
            ("fact_price_daily", FactPriceDaily),
            ("fact_investor_flow_daily", FactInvestorFlowDaily),
            ("fact_foreign_holding_daily", FactForeignHoldingDaily),
        ]:
            states = s.execute(
                select(model.freshness_state, func.count())
                .group_by(model.freshness_state)
            ).all()
            for state, cnt in states:
                if state is None:
                    report.add(
                        "freshness",
                        SEVERITY_ERROR,
                        f"{name} has {cnt} rows with NULL freshness_state",
                    )
                elif state not in _VALID_FRESHNESS:
                    report.add(
                        "freshness",
                        SEVERITY_ERROR,
                        f"{name} has {cnt} rows with invalid freshness_state "
                        f"'{state}'",
                    )

    def _check_coverage(
        self, s, report: ValidationReport, tickers: list[str] | None
    ) -> None:
        """Investor-flow and foreign-holding dates should cover price dates."""
        price_rows = s.execute(
            select(FactPriceDaily.ticker, FactPriceDaily.date)
        ).all()
        if not price_rows:
            return
        price_dates: dict[str, set[date]] = {}
        for tkr, d in price_rows:
            price_dates.setdefault(tkr, set()).add(d)

        target = set(tickers) if tickers else set(price_dates)

        # Flow coverage: each MVP group should have a row per price date.
        flow_rows = s.execute(
            select(
                FactInvestorFlowDaily.ticker,
                FactInvestorFlowDaily.date,
                FactInvestorFlowDaily.investor_group,
            )
        ).all()
        flow_dates: dict[tuple[str, str], set[date]] = {}
        for tkr, d, grp in flow_rows:
            flow_dates.setdefault((tkr, grp), set()).add(d)

        for tkr in target & set(price_dates):
            for grp in MVP_INVESTOR_GROUPS:
                missing = price_dates[tkr] - flow_dates.get((tkr, grp.value), set())
                if missing:
                    report.add(
                        "coverage",
                        SEVERITY_WARNING,
                        f"{tkr}/{grp.value}: {len(missing)} price date(s) "
                        f"without investor-flow rows",
                        ticker=tkr,
                    )

        # Foreign-holding coverage (only if any foreign rows exist).
        fh_rows = s.execute(
            select(FactForeignHoldingDaily.ticker, FactForeignHoldingDaily.date)
        ).all()
        if fh_rows:
            fh_dates: dict[str, set[date]] = {}
            for tkr, d in fh_rows:
                fh_dates.setdefault(tkr, set()).add(d)
            for tkr in target & set(price_dates):
                missing = price_dates[tkr] - fh_dates.get(tkr, set())
                if missing:
                    report.add(
                        "coverage",
                        SEVERITY_WARNING,
                        f"{tkr}: {len(missing)} price date(s) without "
                        f"foreign-holding rows",
                        ticker=tkr,
                    )


def find_duplicate_keys(rows: list[tuple]) -> list[tuple]:
    """Pure helper: return key tuples that appear more than once.

    Exposed for unit testing without a database.
    """
    counter = Counter(rows)
    return [key for key, n in counter.items() if n > 1]
