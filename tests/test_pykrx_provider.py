"""Offline tests for the pykrx provider (mocked KRX, no network).

These pin the column mappings and the real-world hardening discovered against
pykrx 1.2.8: OHLCV has no 거래대금 (trading value derived), and KRX endpoints
may return empty DataFrames (graceful [] instead of crashing).
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from kospi_flow.core.enums import InvestorGroup
from kospi_flow.data.providers import pykrx_provider as P
from kospi_flow.data.providers.pykrx_provider import PykrxProvider, _safe_float

IDX = pd.DatetimeIndex([pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-03")])


class FakeStock:
    """Mimics the subset of pykrx.stock the provider uses."""

    def __init__(self, empty: set[str] | None = None):
        self.empty = empty or set()

    def _maybe(self, key, df):
        return df.iloc[0:0] if key in self.empty else df

    # OHLCV deliberately omits 거래대금 (matches real pykrx 1.2.8).
    def get_market_ohlcv(self, s, e, t):
        return self._maybe("ohlcv", pd.DataFrame(
            {"시가": [78200, 78500], "고가": [79800, 78800], "저가": [78200, 77000],
             "종가": [79600, 77000], "거래량": [17142847, 21753644],
             "등락률": [1.40, -3.27]}, index=IDX))

    def get_market_cap(self, s, e, t):
        return self._maybe("cap", pd.DataFrame(
            {"시가총액": [4.75e14, 4.60e14], "거래량": [17142847, 21753644],
             "상장주식수": [5969782550, 5969782550]}, index=IDX))

    def get_market_trading_value_by_date(self, s, e, t):
        return self._maybe("value", pd.DataFrame(
            {"개인": [1.0e9, -2.0e9], "기관합계": [-5.0e8, 1.0e9],
             "외국인": [-5.0e8, 1.0e9]}, index=IDX))

    def get_market_trading_volume_by_date(self, s, e, t):
        return self._maybe("volume", pd.DataFrame(
            {"개인": [1000, -2000], "기관합계": [-500, 1000],
             "외국인": [-500, 1000]}, index=IDX))

    def get_exhaustion_rates_of_foreign_investment(self, s, e, t):
        return self._maybe("foreign", pd.DataFrame(
            {"보유수량": [3.0e9, 3.01e9], "지분율": [50.5, 50.6],
             "한도수량": [5.97e9, 5.97e9], "한도소진률": [50.5, 50.6]}, index=IDX))

    def get_market_ticker_list(self, market="KOSPI"):
        return ["005930", "005935"]

    def get_market_ticker_name(self, t):
        return {"005930": "삼성전자", "005935": "삼성전자우"}[t]

    def get_index_ohlcv(self, s, e, code):
        return self._maybe("index", pd.DataFrame(
            {"시가": [2669.81, 2675.0], "고가": [2680.0, 2690.0],
             "저가": [2660.0, 2670.0], "종가": [2675.0, 2685.0],
             "등락률": [0.20, 0.37]}, index=IDX))

    def get_index_ticker_name(self, code):
        return "코스피"


@pytest.fixture
def patched(monkeypatch):
    def _use(stock):
        monkeypatch.setattr(P, "_require_pykrx", lambda: stock)
        monkeypatch.setattr(P.time, "sleep", lambda *_a, **_k: None)
    return _use


def test_safe_float():
    assert _safe_float(None) is None
    assert _safe_float("x") is None
    assert _safe_float(float("nan")) is None
    assert _safe_float("3.5") == 3.5
    assert _safe_float(5) == 5.0


def test_price_derives_trading_value_when_missing(patched):
    patched(FakeStock())
    rows = PykrxProvider().get_price_daily("005930", date(2024, 1, 2), date(2024, 1, 3))
    assert len(rows) == 2
    r0 = rows[0]
    assert r0.close == 79600 and r0.adj_close == 79600
    # 거래대금 absent -> derived as close * volume.
    assert r0.trading_value == 79600 * 17142847
    assert r0.market_cap == 4.75e14
    assert r0.shares_outstanding == 5969782550
    assert abs(r0.return_1d - 0.0140) < 1e-9


def test_price_handles_empty_market_cap(patched):
    patched(FakeStock(empty={"cap"}))
    rows = PykrxProvider().get_price_daily("005930", date(2024, 1, 2), date(2024, 1, 3))
    assert len(rows) == 2
    # Cap endpoint blocked -> price still ingested, cap fields None.
    assert rows[0].market_cap is None
    assert rows[0].shares_outstanding is None
    assert rows[0].trading_value is not None


def test_price_empty_ohlcv_returns_empty(patched):
    patched(FakeStock(empty={"ohlcv"}))
    assert PykrxProvider().get_price_daily("005930", date(2024, 1, 2), date(2024, 1, 3)) == []


def test_investor_flow_mapping(patched):
    patched(FakeStock())
    rows = PykrxProvider().get_investor_flow_daily(
        "005930", date(2024, 1, 2), date(2024, 1, 3)
    )
    groups = {r.investor_group for r in rows}
    assert InvestorGroup.RETAIL.value in groups
    assert InvestorGroup.INSTITUTION.value in groups
    assert InvestorGroup.FOREIGN.value in groups
    retail0 = next(r for r in rows if r.investor_group == "retail")
    assert retail0.net_buy_amount == 1.0e9
    assert retail0.net_buy_volume == 1000


def test_investor_flow_empty_returns_empty(patched):
    patched(FakeStock(empty={"value"}))
    assert PykrxProvider().get_investor_flow_daily(
        "005930", date(2024, 1, 2), date(2024, 1, 3)
    ) == []


def test_foreign_holding_mapping_and_pct(patched):
    patched(FakeStock())
    rows = PykrxProvider().get_foreign_holding_daily(
        "005930", date(2024, 1, 2), date(2024, 1, 3)
    )
    assert len(rows) == 2
    assert rows[0].foreign_held_shares == 3.0e9
    assert abs(rows[0].foreign_ownership_pct - 0.505) < 1e-9  # 50.5% -> 0.505
    assert abs(rows[0].foreign_limit_exhaustion_pct - 0.505) < 1e-9


def test_universe_flags_preferred(patched):
    patched(FakeStock())
    metas = PykrxProvider().get_ticker_universe("KOSPI")
    by = {m.ticker: m for m in metas}
    assert by["005935"].is_preferred is True
    assert by["005930"].is_preferred is False


def test_index_ohlcv_mapping(patched):
    patched(FakeStock())
    rows = PykrxProvider().get_index_ohlcv("1001", date(2024, 1, 2), date(2024, 1, 3))
    assert len(rows) == 2
    r0 = rows[0]
    assert r0.index_code == "1001" and r0.name == "코스피"
    assert r0.close == 2675.0
    assert abs(r0.return_1d - 0.0020) < 1e-9  # 0.20% -> 0.0020


def test_index_empty_returns_empty(patched):
    patched(FakeStock(empty={"index"}))
    assert PykrxProvider().get_index_ohlcv(
        "1001", date(2024, 1, 2), date(2024, 1, 3)
    ) == []


def test_default_request_delay_from_settings():
    # Default pacing comes from Settings.pykrx_request_delay (0.3).
    assert PykrxProvider().request_delay == 0.3


def test_request_delay_paces_krx_calls(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(P, "_require_pykrx", lambda: FakeStock())
    monkeypatch.setattr(P.time, "sleep", lambda d: sleeps.append(d))
    PykrxProvider(request_delay=0.5).get_price_daily(
        "005930", date(2024, 1, 2), date(2024, 1, 3)
    )
    # Each KRX endpoint call is paced by the configured delay.
    assert 0.5 in sleeps


def test_fetch_retries_then_succeeds(patched, monkeypatch):
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            return pd.DataFrame()  # empty -> retry
        return pd.DataFrame({"x": [1]}, index=[pd.Timestamp("2024-01-02")])

    monkeypatch.setattr(P.time, "sleep", lambda *_a, **_k: None)
    out = P._fetch("test", flaky)
    assert out is not None and calls["n"] == 3
