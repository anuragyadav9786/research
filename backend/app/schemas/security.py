"""Response schemas for cross-fund security lookup — "which schemes hold
this security", the reverse of app/schemas/portfolio.py's per-scheme view.
"""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class SecuritySummary(BaseModel):
    id: int
    name: str
    isin: str | None
    instrument_type: str | None
    sector: str | None


class SecuritySearchResponse(BaseModel):
    items: list[SecuritySummary]


class HolderRow(BaseModel):
    scheme_id: int
    scheme_name: str
    amc_name: str
    as_of_date: date
    weight_pct: float
    market_value: float | None


class SecurityHoldersResponse(BaseModel):
    security: SecuritySummary
    holders: list[HolderRow]
    total_holders: int
