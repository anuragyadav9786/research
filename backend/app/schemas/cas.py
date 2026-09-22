"""Response shape for CAS (Consolidated Account Statement) upload/parse —
see data_pipeline/normalization/cas_parser.py and app/services/cas_service.py.
"""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

CAS_DISCLAIMER = (
    "Holdings and values are read directly from your uploaded statement as of the date it "
    "was generated — they are not refreshed live and may not reflect transactions since then. "
    "A scheme not yet in our fund database is excluded from analysis, never guessed at."
)


class CASMatchedHolding(BaseModel):
    fund_id: int
    scheme_name: str = Field(..., description="This platform's own name for the matched scheme")
    isin: str
    market_value: float = Field(..., description="Market value as stated in the CAS, as of its generation date")
    weight_pct: float = Field(..., description="market_value as a % of the total across every matched holding")


class CASUnmatchedHolding(BaseModel):
    scheme_name: str = Field(..., description="The scheme name as it appears in the CAS itself")
    isin: str
    market_value: float
    reason: str = Field(..., description="Why this holding couldn't be included, e.g. 'isin_not_found'")


class CASParseResponse(BaseModel):
    as_of_date: date | None = Field(None, description="The statement's own generation/end date, if found")
    matched_holdings: list[CASMatchedHolding]
    unmatched_holdings: list[CASUnmatchedHolding]
    total_market_value: float = Field(..., description="Sum of every currently-held position found in the statement")
    matched_market_value: float = Field(..., description="Sum of only the matched holdings — what weight_pct is based on")
    disclaimer: str = CAS_DISCLAIMER
