"""Shared enumerations.

These are intentionally plain string enums so they serialise cleanly to the
database (stored as text columns) and to JSON in later API phases.
"""

from __future__ import annotations

from enum import Enum


class FreshnessState(str, Enum):
    """Per-row data completion state.

    A daily row is promoted through these states as more authoritative data
    becomes available after the KOSPI close (see context doc, section 5).
    """

    PRELIMINARY = "PRELIMINARY"
    FIRST_EOD = "FIRST_EOD"
    FINAL_EOD = "FINAL_EOD"
    RECONCILED = "RECONCILED"
    ERROR = "ERROR"


class InvestorGroup(str, Enum):
    """Investor groups for ``fact_investor_flow_daily``.

    Only ``RETAIL``, ``INSTITUTION``, and ``FOREIGN`` are required for the MVP;
    the remaining values are reserved for richer breakdowns later.
    """

    RETAIL = "retail"
    INSTITUTION = "institution"
    FOREIGN = "foreign"
    OTHER_CORPORATION = "other_corporation"
    OTHER_FOREIGN = "other_foreign"
    FINANCIAL_INVESTMENT = "financial_investment"
    INSURANCE = "insurance"
    TRUST = "trust"
    PRIVATE_EQUITY = "private_equity"
    BANK = "bank"
    PENSION_FUND = "pension_fund"


#: Investor groups that must be populated for every ingested stock in the MVP.
MVP_INVESTOR_GROUPS: tuple[InvestorGroup, ...] = (
    InvestorGroup.RETAIL,
    InvestorGroup.INSTITUTION,
    InvestorGroup.FOREIGN,
)

#: Korean display labels. Centralised here so the UI never mislabels net-buy
#: flow as actual holdings (context doc, section 3).
INVESTOR_GROUP_LABELS_KR: dict[InvestorGroup, str] = {
    InvestorGroup.RETAIL: "개인",
    InvestorGroup.INSTITUTION: "기관",
    InvestorGroup.FOREIGN: "외국인",
}
