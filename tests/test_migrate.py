"""DB URL normalization + cross-database copy (for SQLite → Postgres deploys)."""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, select

from kospi_flow.core.db import Database, normalize_db_url
from kospi_flow.core.models import DimStock, FactPriceDaily
from kospi_flow.jobs.migrate import copy_database


def test_normalize_db_url():
    assert normalize_db_url("postgres://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert normalize_db_url("postgresql://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    # Already-qualified and sqlite pass through unchanged.
    assert normalize_db_url("postgresql+psycopg://u@h/db") == "postgresql+psycopg://u@h/db"
    assert normalize_db_url("sqlite:///./x.db") == "sqlite:///./x.db"


def test_copy_database_between_sqlite_files(tmp_path):
    src_url = f"sqlite:///{(tmp_path / 'src.db').as_posix()}"
    dst_url = f"sqlite:///{(tmp_path / 'dst.db').as_posix()}"

    src = Database(src_url)
    src.create_all()
    with src.session() as s:
        s.add(DimStock(ticker="005930", name_kr="삼성전자", market="KOSPI"))
        s.add(FactPriceDaily(date=date(2024, 1, 2), ticker="005930", close=79600.0))
        s.add(FactPriceDaily(date=date(2024, 1, 3), ticker="005930", close=77000.0))

    counts = copy_database(src_url, dst_url, batch=1000)
    assert counts["dim_stock"] == 1
    assert counts["fact_price_daily"] == 2

    dst = Database(dst_url)
    with dst.session() as s:
        assert s.scalar(select(func.count()).select_from(FactPriceDaily)) == 2
        row = s.get(FactPriceDaily, (date(2024, 1, 2), "005930"))
        assert row is not None and row.close == 79600.0
