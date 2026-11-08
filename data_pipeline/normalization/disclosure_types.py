"""Canonical, AMC-agnostic shapes a monthly portfolio-disclosure parser
produces, consumed by data_pipeline/orchestration/disclosure_ingestion_common.py.

Lives in its own module (not inside any one AMC's parser file) because
once a second AMC parser exists, having it import these from a module
literally named after the first AMC would be backwards -- the shared
vocabulary needs a neutral home. absl_disclosure_parser.py re-exports
these for backward compatibility with existing imports.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class DisclosureHolding:
    instrument_name: str
    isin: str | None
    sector: str | None
    credit_rating: str | None
    quantity: float | None
    market_value_rupees: float
    weight_pct: float
    ytm_pct: float | None
    ytc_pct: float | None
    instrument_type: str


@dataclass
class DisclosureScheme:
    short_code: str
    scheme_name: str
    as_of_date: date
    holdings: list[DisclosureHolding] = field(default_factory=list)
    # Real rows a parser couldn't confidently parse/classify -- reported,
    # not silently dropped, same discipline cas_parser.py's own unmatched
    # list follows. Each entry is a short human-readable reason tied to
    # the row's own instrument-name text.
    skipped_rows: list[str] = field(default_factory=list)


@dataclass
class IndexEntry:
    scheme_code: str
    short_code: str
    scheme_name: str
