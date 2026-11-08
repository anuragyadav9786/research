"""Response schemas for AMC/fund-family browsing — the AMC-level
equivalent of app/schemas/funds.py's scheme-level shapes.
"""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class AmcSummary(BaseModel):
    id: int
    name: str
    fund_family_count: int
    scheme_count: int
    schemes_with_holdings_count: int


class AmcListResponse(BaseModel):
    items: list[AmcSummary]


class AmcSchemeRow(BaseModel):
    id: int
    scheme_name: str
    category: str
    fund_family_name: str
    benchmark_name: str | None
    holdings_as_of_date: date | None


class AmcDetailResponse(BaseModel):
    id: int
    name: str
    schemes: list[AmcSchemeRow]
