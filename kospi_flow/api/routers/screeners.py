"""Screener endpoints (context doc §8, §12.1)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from kospi_flow.analytics.screener import ScreenerCriteria, run_screener
from kospi_flow.api.deps import get_session
from kospi_flow.api.envelope import envelope, make_metadata
from kospi_flow.api.schemas import ScreenerRequest
from kospi_flow.core.enums import InvestorGroup

router = APIRouter(prefix="/screeners", tags=["screeners"])


def _criteria(req: ScreenerRequest) -> ScreenerCriteria:
    return ScreenerCriteria(
        market=req.market,
        lookback_days=req.lookback_days,
        investor_groups=req.investor_groups,
        min_net_buy_amount=req.min_net_buy_amount,
        min_net_buy_pct_mcap=req.min_net_buy_pct_mcap,
        min_net_buy_volume_pct_shares=req.min_net_buy_volume_pct_shares,
        min_consecutive_days=req.min_consecutive_days,
        min_avg_trading_value=req.min_avg_trading_value,
        exclude_preferred=req.exclude_preferred,
        limit=req.limit,
    )


def _run(req: ScreenerRequest, session: Session) -> dict:
    rows = run_screener(session, _criteria(req))
    return envelope(
        [r.as_dict() for r in rows],
        make_metadata(
            extra_count=len(rows),
            lookback_days=req.lookback_days,
            investor_groups=req.investor_groups,
        ),
    )


@router.post("/investor-flow")
def screen_investor_flow(
    req: ScreenerRequest, session: Session = Depends(get_session)
) -> dict:
    return _run(req, session)


@router.post("/streaks")
def screen_streaks(
    req: ScreenerRequest, session: Session = Depends(get_session)
) -> dict:
    """Consecutive net-buy streak screener (defaults to ≥3 day streak)."""
    if req.min_consecutive_days is None:
        req = req.model_copy(update={"min_consecutive_days": 3})
    return _run(req, session)


@router.post("/foreign-institution-co-buy")
def screen_co_buy(
    req: ScreenerRequest, session: Session = Depends(get_session)
) -> dict:
    """외국인+기관 co-buy screener: both groups summed, positive net buy."""
    req = req.model_copy(
        update={
            "investor_groups": [
                InvestorGroup.FOREIGN.value,
                InvestorGroup.INSTITUTION.value,
            ],
            "min_net_buy_amount": req.min_net_buy_amount
            if req.min_net_buy_amount is not None
            else 0.0,
        }
    )
    return _run(req, session)
