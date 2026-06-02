"""Validation utilities: clean data passes, problems are detected."""

from __future__ import annotations

from datetime import date

from sqlalchemy import delete

from kospi_flow.core.db import Database
from kospi_flow.core.enums import FreshnessState, InvestorGroup
from kospi_flow.core.models import FactInvestorFlowDaily, FactPriceDaily
from kospi_flow.data.ingestion import Ingestor
from kospi_flow.data.providers import get_provider
from kospi_flow.data.validation import DataValidator, find_duplicate_keys

TICKER = "005930"


def _seed(db: Database, tmp_path, monkeypatch):
    provider = get_provider("sample")
    ing = Ingestor(provider, db, freshness_state=FreshnessState.FINAL_EOD)
    monkeypatch.setattr(ing.settings, "raw_data_path", tmp_path / "raw")
    ing.run(date(2021, 1, 4), date(2021, 2, 26), tickers=[TICKER])
    return ing


def test_clean_data_has_no_errors(db: Database, tmp_path, monkeypatch):
    _seed(db, tmp_path, monkeypatch)
    report = DataValidator(db).validate()
    assert report.ok, report.summary()
    assert report.counts["fact_price_daily"] > 0


def test_missing_flow_rows_flagged_as_coverage_warning(
    db: Database, tmp_path, monkeypatch
):
    _seed(db, tmp_path, monkeypatch)
    # Delete all foreign flow rows -> coverage gap for that group.
    with db.session() as s:
        s.execute(
            delete(FactInvestorFlowDaily).where(
                FactInvestorFlowDaily.investor_group
                == InvestorGroup.FOREIGN.value
            )
        )
    report = DataValidator(db).validate()
    coverage = [i for i in report.warnings if i.check == "coverage"]
    assert coverage
    assert any("foreign" in i.message for i in coverage)


def test_null_freshness_flagged_as_error(db: Database, tmp_path, monkeypatch):
    _seed(db, tmp_path, monkeypatch)
    with db.session() as s:
        row = s.query(FactPriceDaily).first()
        row.freshness_state = None
    report = DataValidator(db).validate()
    assert not report.ok
    assert any(i.check == "freshness" for i in report.errors)


def test_empty_database_reports_errors(db: Database):
    report = DataValidator(db).validate()
    assert not report.ok
    assert any(i.check == "row_presence" for i in report.errors)


def test_find_duplicate_keys_pure_helper():
    rows = [("2021-01-04", "005930"), ("2021-01-04", "005930"), ("2021-01-05", "x")]
    assert find_duplicate_keys(rows) == [("2021-01-04", "005930")]
