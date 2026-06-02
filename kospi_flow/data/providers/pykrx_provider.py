"""pykrx-backed prototype provider.

Pulls real KOSPI data via the ``pykrx`` library. This is acceptable for the
MVP/prototype only; production must use an official/licensed source (context
doc, sections 4 and 17). ``pykrx`` is an optional dependency — install it with
``pip install pykrx`` and select it via ``KOSPI_DATA_SOURCE=pykrx``.

Real-world notes (validated 2026-05-31 against pykrx 1.2.8):
  * ``get_market_ohlcv`` (single ticker, date range) returns
    [시가, 고가, 저가, 종가, 거래량, 등락률] — there is NO 거래대금 column, so
    trading value is derived as close × volume when absent.
  * The KRX market-cap / investor-trading / foreign-holding endpoints are
    rate-limited and frequently return EMPTY responses for non-Korean or
    datacenter IPs. Each call is retried with backoff; on persistent failure the
    method logs a warning and returns ``[]`` rather than crashing the pipeline.
  * All numeric coercion is None/NaN-safe so missing columns never raise.
"""

from __future__ import annotations

import time
from datetime import date
from typing import Any, Callable

from kospi_flow.core.logging import get_logger
from kospi_flow.core.enums import InvestorGroup
from kospi_flow.data.providers.base import (
    ForeignHoldingRow,
    IndexRow,
    InvestorFlowRow,
    MarketDataProvider,
    PriceRow,
    StockMeta,
)

logger = get_logger(__name__)

_DATE_FMT = "%Y%m%d"
_RETRY_ATTEMPTS = 3
_RETRY_BACKOFF = 1.5  # seconds, multiplied by attempt index

# pykrx investor labels (Korean) -> our enum values, MVP subset.
_PYKRX_INVESTOR_MAP = {
    "개인": InvestorGroup.RETAIL,
    "기관합계": InvestorGroup.INSTITUTION,
    "외국인": InvestorGroup.FOREIGN,
    "외국인합계": InvestorGroup.FOREIGN,
}


def _require_pykrx():
    try:
        from pykrx import stock  # type: ignore
    except ImportError as exc:  # pragma: no cover - depends on optional dep
        raise ImportError(
            "The 'pykrx' provider requires the optional dependency 'pykrx'. "
            "Install it with `pip install pykrx`, or use KOSPI_DATA_SOURCE=sample."
        ) from exc
    return stock


def _safe_float(value: Any) -> float | None:
    """Coerce to float, returning None for None/NaN/blank/unparseable values."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    # NaN check without importing numpy/pandas here.
    if f != f:
        return None
    return f


def _fetch(label: str, fn: Callable[[], Any], required: bool = False, pace: float = 0.0):
    """Call ``fn`` with retry/backoff; tolerate empty/blocked KRX responses.

    ``pace`` sleeps before the first attempt to stay under KRX rate limits.
    Returns the result, or ``None`` if every attempt failed or returned empty.
    Raises only when ``required`` and all attempts fail with an exception.
    """
    if pace > 0:
        time.sleep(pace)
    last_exc: Exception | None = None
    for attempt in range(1, _RETRY_ATTEMPTS + 1):
        try:
            df = fn()
            if df is not None and getattr(df, "empty", False) is False and len(df):
                return df
            logger.warning(
                "pykrx %s returned empty (attempt %d/%d) — KRX may be "
                "rate-limiting or blocking this endpoint/IP.",
                label,
                attempt,
                _RETRY_ATTEMPTS,
            )
        except Exception as exc:  # noqa: BLE001 - external API boundary
            last_exc = exc
            logger.warning(
                "pykrx %s failed (attempt %d/%d): %s",
                label,
                attempt,
                _RETRY_ATTEMPTS,
                exc,
            )
        if attempt < _RETRY_ATTEMPTS:
            time.sleep(_RETRY_BACKOFF * attempt)
    if required and last_exc is not None:
        raise last_exc
    logger.warning("pykrx %s unavailable after retries; returning no rows.", label)
    return None


class PykrxProvider(MarketDataProvider):
    """Real KOSPI data via pykrx (prototype only)."""

    name = "pykrx"
    supports_foreign_holdings = True
    supports_index = True

    def __init__(self, request_delay: float | None = None) -> None:
        if request_delay is None:
            from kospi_flow.core.config import get_settings

            request_delay = get_settings().pykrx_request_delay
        #: Seconds paused before each KRX call to avoid rate-limit empties.
        self.request_delay = max(0.0, float(request_delay))

    def _get(self, label: str, fn: Callable[[], Any]):
        return _fetch(label, fn, pace=self.request_delay)

    def get_ticker_universe(self, market: str = "KOSPI") -> list[StockMeta]:
        stock = _require_pykrx()
        tickers = self._get(
            "ticker_list", lambda: stock.get_market_ticker_list(market=market)
        )
        if not tickers:
            return []
        out: list[StockMeta] = []
        for t in tickers:
            try:
                name = stock.get_market_ticker_name(t)
            except Exception:  # noqa: BLE001
                name = None
            out.append(
                StockMeta(
                    ticker=t,
                    name_kr=name,
                    market=market,
                    is_preferred=bool(name) and name.endswith("우"),
                    is_active=True,
                )
            )
        return out

    def get_price_daily(
        self, ticker: str, start: date, end: date
    ) -> list[PriceRow]:
        stock = _require_pykrx()
        s, e = start.strftime(_DATE_FMT), end.strftime(_DATE_FMT)
        ohlcv = self._get("ohlcv", lambda: stock.get_market_ohlcv(s, e, ticker))
        if ohlcv is None:
            return []
        # Market cap / shares are a separate (often-blocked) endpoint.
        cap = self._get("market_cap", lambda: stock.get_market_cap(s, e, ticker))

        rows: list[PriceRow] = []
        for idx, r in ohlcv.iterrows():
            close = _safe_float(r.get("종가"))
            volume = _safe_float(r.get("거래량"))
            # 거래대금 is absent from single-ticker OHLCV; derive when missing.
            trading_value = _safe_float(r.get("거래대금"))
            if trading_value is None and close is not None and volume is not None:
                trading_value = close * volume

            cap_row = None
            if cap is not None and idx in cap.index:
                cap_row = cap.loc[idx]
            chg = _safe_float(r.get("등락률"))

            rows.append(
                PriceRow(
                    date=idx.date(),
                    ticker=ticker,
                    open=_safe_float(r.get("시가")),
                    high=_safe_float(r.get("고가")),
                    low=_safe_float(r.get("저가")),
                    close=close,
                    # pykrx OHLCV is corporate-action adjusted by default.
                    adj_close=close,
                    volume=volume,
                    trading_value=trading_value,
                    market_cap=(
                        _safe_float(cap_row.get("시가총액"))
                        if cap_row is not None
                        else None
                    ),
                    shares_outstanding=(
                        _safe_float(cap_row.get("상장주식수"))
                        if cap_row is not None
                        else None
                    ),
                    return_1d=(chg / 100.0 if chg is not None else None),
                )
            )
        return rows

    def get_investor_flow_daily(
        self, ticker: str, start: date, end: date
    ) -> list[InvestorFlowRow]:
        stock = _require_pykrx()
        s, e = start.strftime(_DATE_FMT), end.strftime(_DATE_FMT)
        amt = self._get(
            "trading_value_by_date",
            lambda: stock.get_market_trading_value_by_date(s, e, ticker),
        )
        if amt is None:
            return []
        vol = self._get(
            "trading_volume_by_date",
            lambda: stock.get_market_trading_volume_by_date(s, e, ticker),
        )

        rows: list[InvestorFlowRow] = []
        for kr_label, group in _PYKRX_INVESTOR_MAP.items():
            if kr_label not in amt.columns:
                continue
            for idx in amt.index:
                net_amt = _safe_float(amt.loc[idx, kr_label])
                net_vol = None
                if vol is not None and kr_label in vol.columns and idx in vol.index:
                    net_vol = _safe_float(vol.loc[idx, kr_label])
                rows.append(
                    InvestorFlowRow(
                        date=idx.date(),
                        ticker=ticker,
                        investor_group=group.value,
                        net_buy_amount=net_amt,
                        net_buy_volume=net_vol,
                    )
                )
        return rows

    def get_foreign_holding_daily(
        self, ticker: str, start: date, end: date
    ) -> list[ForeignHoldingRow]:
        stock = _require_pykrx()
        s, e = start.strftime(_DATE_FMT), end.strftime(_DATE_FMT)
        df = self._get(
            "foreign_exhaustion",
            lambda: stock.get_exhaustion_rates_of_foreign_investment(s, e, ticker),
        )
        if df is None:
            return []
        rows: list[ForeignHoldingRow] = []
        for idx, r in df.iterrows():
            pct = _safe_float(r.get("지분율"))
            exh = _safe_float(r.get("한도소진률"))
            rows.append(
                ForeignHoldingRow(
                    date=idx.date(),
                    ticker=ticker,
                    foreign_held_shares=_safe_float(r.get("보유수량")),
                    foreign_ownership_pct=(pct / 100.0 if pct is not None else None),
                    foreign_limit_shares=_safe_float(r.get("한도수량")),
                    foreign_limit_exhaustion_pct=(
                        exh / 100.0 if exh is not None else None
                    ),
                )
            )
        return rows

    def get_index_ohlcv(
        self, index_code: str, start: date, end: date
    ) -> list[IndexRow]:
        """KOSPI index OHLC via pykrx (index code ``1001`` = 코스피).

        Columns observed: [시가, 고가, 저가, 종가, 거래량, 거래대금, 상장시가총액,
        등락률] (varies by version). Mapped None-safely; like the other KRX
        endpoints it may be blocked from non-Korean IPs and return ``[]``.
        """
        stock = _require_pykrx()
        s, e = start.strftime(_DATE_FMT), end.strftime(_DATE_FMT)
        df = self._get(
            "index_ohlcv", lambda: stock.get_index_ohlcv(s, e, index_code)
        )
        if df is None:
            return []
        name = None
        try:
            name = stock.get_index_ticker_name(index_code)
        except Exception:  # noqa: BLE001
            name = None
        rows: list[IndexRow] = []
        for idx, r in df.iterrows():
            chg = _safe_float(r.get("등락률"))
            rows.append(
                IndexRow(
                    date=idx.date(),
                    index_code=index_code,
                    name=name,
                    open=_safe_float(r.get("시가")),
                    high=_safe_float(r.get("고가")),
                    low=_safe_float(r.get("저가")),
                    close=_safe_float(r.get("종가")),
                    return_1d=(chg / 100.0 if chg is not None else None),
                )
            )
        return rows
