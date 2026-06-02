"""User watchlist endpoints (Phase 5).

No authentication in the MVP — a watchlist is identified by its name. Provides
CRUD plus a convenience ``/flows`` view summarising recent investor flow for the
watchlisted tickers.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from kospi_flow.api.deps import get_session
from kospi_flow.api.envelope import ApiError, envelope, make_metadata, not_found
from kospi_flow.api.schemas import WatchlistCreate, WatchlistItemAdd
from kospi_flow.core.enums import MVP_INVESTOR_GROUPS
from kospi_flow.core.models import (
    DimStock,
    FactInvestorFlowDaily,
    FactPriceDaily,
    Watchlist,
    WatchlistItem,
)

router = APIRouter(prefix="/watchlists", tags=["watchlists"])


def _require_watchlist(session: Session, name: str) -> Watchlist:
    wl = session.get(Watchlist, name)
    if wl is None:
        raise not_found(f"Unknown watchlist '{name}'.", name=name)
    return wl


def _items(session: Session, name: str) -> list[str]:
    return [
        t for (t,) in session.execute(
            select(WatchlistItem.ticker)
            .where(WatchlistItem.watchlist_name == name)
            .order_by(WatchlistItem.ticker)
        ).all()
    ]


@router.get("")
def list_watchlists(session: Session = Depends(get_session)) -> dict:
    rows = session.execute(
        select(
            Watchlist.name,
            Watchlist.description,
            func.count(WatchlistItem.ticker),
        )
        .join(WatchlistItem, WatchlistItem.watchlist_name == Watchlist.name, isouter=True)
        .group_by(Watchlist.name, Watchlist.description)
        .order_by(Watchlist.name)
    ).all()
    data = [{"name": n, "description": d, "count": c} for (n, d, c) in rows]
    return envelope(data, make_metadata())


@router.post("", status_code=201)
def create_watchlist(
    req: WatchlistCreate, session: Session = Depends(get_session)
) -> dict:
    if session.get(Watchlist, req.name) is not None:
        raise ApiError(409, "ALREADY_EXISTS", f"Watchlist '{req.name}' already exists.")
    session.add(Watchlist(name=req.name, description=req.description))
    return envelope({"name": req.name, "description": req.description})


@router.get("/{name}")
def get_watchlist(name: str, session: Session = Depends(get_session)) -> dict:
    wl = _require_watchlist(session, name)
    return envelope(
        {"name": wl.name, "description": wl.description, "tickers": _items(session, name)}
    )


@router.delete("/{name}")
def delete_watchlist(name: str, session: Session = Depends(get_session)) -> dict:
    wl = _require_watchlist(session, name)
    session.execute(
        WatchlistItem.__table__.delete().where(WatchlistItem.watchlist_name == name)
    )
    session.delete(wl)
    return envelope({"deleted": name})


@router.post("/{name}/items", status_code=201)
def add_item(
    name: str, req: WatchlistItemAdd, session: Session = Depends(get_session)
) -> dict:
    _require_watchlist(session, name)
    if session.get(DimStock, req.ticker) is None:
        raise not_found(f"Unknown ticker '{req.ticker}'.", ticker=req.ticker)
    if session.get(WatchlistItem, (name, req.ticker)) is None:
        session.add(WatchlistItem(watchlist_name=name, ticker=req.ticker))
    return envelope({"watchlist": name, "tickers": _items(session, name)})


@router.delete("/{name}/items/{ticker}")
def remove_item(
    name: str, ticker: str, session: Session = Depends(get_session)
) -> dict:
    _require_watchlist(session, name)
    item = session.get(WatchlistItem, (name, ticker))
    if item is None:
        raise not_found(f"'{ticker}' not in watchlist '{name}'.", ticker=ticker)
    session.delete(item)
    return envelope({"watchlist": name, "tickers": _items(session, name)})


@router.get("/{name}/flows")
def watchlist_flows(
    name: str, lookback_days: int = 5, session: Session = Depends(get_session)
) -> dict:
    """Recent net-buy summary per investor group for the watchlist tickers."""
    _require_watchlist(session, name)
    tickers = _items(session, name)
    if not tickers:
        return envelope([], make_metadata())
    dates = [
        d for (d,) in session.execute(
            select(FactPriceDaily.date)
            .distinct()
            .order_by(FactPriceDaily.date.desc())
            .limit(lookback_days)
        ).all()
    ]
    rows = session.execute(
        select(
            FactInvestorFlowDaily.ticker,
            FactInvestorFlowDaily.investor_group,
            func.sum(FactInvestorFlowDaily.net_buy_amount),
        )
        .where(FactInvestorFlowDaily.ticker.in_(tickers))
        .where(FactInvestorFlowDaily.date.in_(dates))
        .where(
            FactInvestorFlowDaily.investor_group.in_(
                [g.value for g in MVP_INVESTOR_GROUPS]
            )
        )
        .group_by(FactInvestorFlowDaily.ticker, FactInvestorFlowDaily.investor_group)
    ).all()
    names = dict(session.execute(select(DimStock.ticker, DimStock.name_kr)).all())
    summary: dict[str, dict] = {
        t: {"ticker": t, "name_kr": names.get(t)} for t in tickers
    }
    for ticker, group, net in rows:
        summary[ticker][f"{group}_net_buy"] = float(net or 0.0)
    return envelope(
        list(summary.values()),
        make_metadata(latest_data_date=max(dates) if dates else None),
    )
