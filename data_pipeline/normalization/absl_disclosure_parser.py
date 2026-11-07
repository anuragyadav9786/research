"""Parses Aditya Birla Sun Life's real monthly portfolio-disclosure
workbook (the `.xls` inside the ZIP AMCs publish each month, e.g.
`https://mutualfund.adityabirlacapital.com/.../<date>_abslmf_monthlydisclosure.zip`)
into structured per-scheme holdings.

Confirmed against the real September 2026 file, not guessed: 105 sheets
(one `Index` sheet mapping AMC-internal scheme codes to scheme names,
plus one sheet per scheme, 104 total), every scheme sheet sharing one
uniform 10-column table. Column layout (0-indexed; columns 0 is always
blank):

    1: AMC-internal security code (not used -- no cross-AMC meaning)
    2: Name of the Instrument/Issuer
    3: ISIN
    4: Industry^/Rating -- an AMFI-style equity sector for an equity or
       foreign-security row, an InvIT/REIT sector for a reit_invit row,
       a credit rating (e.g. "CRISIL AAA") for a debt/securitised-debt/
       government-security/money-market row, and blank for everything
       else (mutual fund units, cash-equivalent rows) -- confirmed
       against a real row of each category, never assumed.
    5: Quantity
    6: Market value, in Lakhs of rupees (so always x100000 before
       storing -- see PortfolioHolding.market_value's own docstring)
    7: % to AUM, as a fraction (e.g. 0.0559673 = 5.59673%, so x100
       before storing) -- occasionally a string like "$0.00%" instead
       of a float, when the AMC's own materiality footnote applies
       ("$ Less Than 0.01% of Net Asset Value"); treated as 0.0, not a
       parse failure.
    8: YTM % (debt-like rows only), as a fraction
    9: YTC % (debt-like rows only, usually blank even then), as a
       fraction

Each scheme sheet's holdings are grouped under category-header rows
(e.g. "Equity & Equity Related", "Debt Instruments") with no ISIN/
Quantity/Market-value of their own, interspersed with "Total"/sub-
category rows ("a) Listed...", "Certificate of Deposits", ...) that also
aren't holdings. A row counts as a real holding here purely by having a
genuinely numeric market value -- not by matching any specific label
text -- so an unrecognized sub-header (there are several real ones, not
all enumerated) is skipped for free rather than needing to be listed.
"Total"/"GRAND TOTAL (AUM)" rows are the one exception: they DO carry a
numeric market value, so they're matched and skipped by name instead.

Only the category headers that actually change how a row's data is
interpreted are tracked as state (see `_CATEGORY_INSTRUMENT_TYPES`,
matched against every category header actually seen across all 104
real scheme sheets this was built from) -- a real holding row seen
before any recognized header is reported as unclassified, never
silently guessed into a type.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import xlrd

INDEX_SHEET_NAME = "Index"

# Matched case-insensitively against a category-header row's own name
# text. Ordered so a more specific match (e.g. "international mutual
# fund units") is tried before a shorter one it could also match if the
# shorter one were substring-matched -- kept as exact-contains checks in
# this order to stay unambiguous. Every entry confirmed against a real
# header row in the September 2026 file.
_CATEGORY_INSTRUMENT_TYPES: list[tuple[str, str]] = [
    ("equity & equity related", "equity"),
    ("government securities", "government_security"),
    ("securitised debt", "securitised_debt"),
    ("debt instruments", "debt"),
    ("money market instruments", "money_market"),
    ("international mutual fund units", "mutual_fund_unit"),
    ("mutual fund units", "mutual_fund_unit"),
    ("infrastructure investment trust", "reit_invit"),
    ("real estate investment trust", "reit_invit"),
    ("foreign securities", "foreign_security"),
    ("treps / reverse repo investments", "cash_equivalent"),
    ("other current assets", "cash_equivalent"),
    # Physical gold/silver (the Gold/Silver ETF and FoF schemes' own
    # sub-headers, nested under a generic "Others" parent the same way
    # Infrastructure Investment Trust is elsewhere) -- doesn't fit any of
    # the other specific categories, so "other" rather than inventing a
    # dedicated enum value for what's confirmed to be exactly 4 of 104
    # schemes.
    ("gold", "other"),
    ("silver", "other"),
    # A Fund-of-Funds scheme holding units of another (here, ABSL's own)
    # ETF -- conceptually the same bucket as Mutual Fund Units, just the
    # AMC's own section-header wording for this specific case.
    ("exchange traded fund", "mutual_fund_unit"),
]

# Which of the above instrument types put the Industry^/Rating column's
# text into a sector vs. a credit rating -- confirmed against a real row
# of each category (see module docstring). Anything not in either set
# (mutual_fund_unit, cash_equivalent) gets neither, confirmed blank.
_SECTOR_LIKE_INSTRUMENT_TYPES = {"equity", "reit_invit", "foreign_security"}
_RATING_LIKE_INSTRUMENT_TYPES = {"debt", "securitised_debt", "government_security", "money_market"}

_AS_OF_DATE_RE = re.compile(r"Portfolio Statement as on\s+([A-Za-z]+\s+\d{1,2},\s*\d{4})")
_HEADER_ROW_SEARCH_LIMIT = 15
_INTRO_SEARCH_LIMIT = 10


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
    # Real rows this couldn't confidently parse/classify -- reported, not
    # silently dropped, same discipline cas_parser.py's own unmatched
    # list follows. Each entry is a short human-readable reason tied to
    # the row's own instrument-name text.
    skipped_rows: list[str] = field(default_factory=list)


@dataclass
class IndexEntry:
    scheme_code: str
    short_code: str
    scheme_name: str


def parse_disclosure_workbook(file_bytes: bytes) -> list[DisclosureScheme]:
    """Every scheme sheet in the workbook, parsed. A sheet whose scheme
    name or "Portfolio Statement as on" date can't be found is skipped
    entirely (never guessed) -- this would mean the file's own layout
    has changed in a way this parser doesn't yet understand, not a
    normal/expected condition."""
    book = xlrd.open_workbook(file_contents=file_bytes, on_demand=True)
    schemes: list[DisclosureScheme] = []
    for sheet_name in book.sheet_names():
        if sheet_name == INDEX_SHEET_NAME:
            continue
        sheet = book.sheet_by_name(sheet_name)
        rows = [[sheet.cell(r, c).value for c in range(sheet.ncols)] for r in range(sheet.nrows)]
        scheme = _parse_scheme_sheet_rows(sheet_name, rows)
        if scheme is not None:
            schemes.append(scheme)
    return schemes


def parse_index_sheet(file_bytes: bytes) -> list[IndexEntry]:
    """The `Index` sheet's own (Scheme Code, Scheme Short code, Scheme
    Name) rows -- the AMC's own stable short code is the durable join
    key a scheme-identity mapping should be built against (see
    data_pipeline/normalization/absl_scheme_identity.py), not the full
    scheme name, which can vary in wording between this file and
    whatever name a scheme was originally onboarded under."""
    book = xlrd.open_workbook(file_contents=file_bytes, on_demand=True)
    sheet = book.sheet_by_name(INDEX_SHEET_NAME)
    entries: list[IndexEntry] = []
    for r in range(sheet.nrows):
        code, short_code, name = (sheet.cell(r, c).value for c in range(3))
        if not (isinstance(code, str) and code.strip()) or not (isinstance(short_code, str) and short_code.strip()):
            continue
        if code.strip().lower() == "scheme code":  # the header row itself
            continue
        entries.append(IndexEntry(scheme_code=code.strip(), short_code=short_code.strip(), scheme_name=str(name).strip()))
    return entries


def _parse_scheme_sheet_rows(short_code: str, rows: list[list[Any]]) -> DisclosureScheme | None:
    scheme_name = _extract_scheme_name(rows)
    as_of_date = _extract_as_of_date(rows)
    if not scheme_name or as_of_date is None:
        return None

    header_row = _find_header_row(rows)
    if header_row is None:
        return None

    scheme = DisclosureScheme(short_code=short_code, scheme_name=scheme_name, as_of_date=as_of_date)
    current_instrument_type: str | None = None

    for row in rows[header_row + 1 :]:
        name = row[2] if len(row) > 2 else None
        if not isinstance(name, str) or not name.strip():
            continue
        name_clean = name.strip()
        name_lower = name_clean.lower()

        if name_lower == "grand total (aum)":
            # The real holdings table definitively ends here -- every real
            # scheme sheet has exactly one of these, and everything after
            # it (notes, plan-wise NAV tables, derivatives-exposure
            # sub-tables with their own unrelated column layout) must
            # never be scanned for holdings. Confirmed necessary: without
            # this, a later derivatives sub-table whose first few columns
            # happen to look numeric was mistaken for real holdings.
            break
        if name_lower == "total":
            continue  # a real subtotal, not a holding

        market_value_lakhs = row[6] if len(row) > 6 else None
        if not isinstance(market_value_lakhs, (int, float)):
            # A label/category-header (or unrecognized sub-header) row --
            # category matching only ever applies here, never to a row
            # that already carries real holding-shaped data, so a real
            # holding whose name happens to contain a marker word (e.g.
            # a hypothetical "XYZ Gold Mines Ltd" equity holding) can
            # never be mistaken for a category header.
            matched_type = _match_category_header(name_lower)
            if matched_type is not None:
                current_instrument_type = matched_type
            continue

        if current_instrument_type is None:
            scheme.skipped_rows.append(f"{name_clean!r}: no category header seen yet")
            continue

        weight_pct = _parse_weight_pct(row[7] if len(row) > 7 else None)
        if weight_pct is None:
            scheme.skipped_rows.append(f"{name_clean!r}: unparseable % to AUM")
            continue

        isin_raw = row[3] if len(row) > 3 else None
        isin = isin_raw.strip() if isinstance(isin_raw, str) and isin_raw.strip() else None

        industry_or_rating_raw = row[4] if len(row) > 4 else None
        industry_or_rating = (
            industry_or_rating_raw.strip()
            if isinstance(industry_or_rating_raw, str) and industry_or_rating_raw.strip()
            else None
        )
        sector = industry_or_rating if current_instrument_type in _SECTOR_LIKE_INSTRUMENT_TYPES else None
        credit_rating = industry_or_rating if current_instrument_type in _RATING_LIKE_INSTRUMENT_TYPES else None

        quantity_raw = row[5] if len(row) > 5 else None
        quantity = float(quantity_raw) if isinstance(quantity_raw, (int, float)) else None

        scheme.holdings.append(
            DisclosureHolding(
                instrument_name=name_clean,
                isin=isin,
                sector=sector,
                credit_rating=credit_rating,
                quantity=quantity,
                market_value_rupees=float(market_value_lakhs) * 100_000,
                weight_pct=weight_pct,
                ytm_pct=_parse_pct_fraction(row[8] if len(row) > 8 else None),
                ytc_pct=_parse_pct_fraction(row[9] if len(row) > 9 else None),
                instrument_type=current_instrument_type,
            )
        )

    return scheme


def _extract_scheme_name(rows: list[list[Any]]) -> str | None:
    if not rows:
        return None
    first_row = rows[0]
    name = first_row[2] if len(first_row) > 2 else None
    return name.strip() if isinstance(name, str) and name.strip() else None


def _extract_as_of_date(rows: list[list[Any]]) -> date | None:
    for row in rows[:_INTRO_SEARCH_LIMIT]:
        for cell in row:
            if not isinstance(cell, str):
                continue
            match = _AS_OF_DATE_RE.search(cell)
            if match:
                try:
                    return datetime.strptime(match.group(1), "%B %d, %Y").date()
                except ValueError:
                    return None
    return None


def _find_header_row(rows: list[list[Any]]) -> int | None:
    for i, row in enumerate(rows[:_HEADER_ROW_SEARCH_LIMIT]):
        row_text = " ".join(str(c) for c in row)
        if "ISIN" in row_text and "Instrument" in row_text:
            return i
    return None


def _match_category_header(name_lower: str) -> str | None:
    for marker, instrument_type in _CATEGORY_INSTRUMENT_TYPES:
        if marker in name_lower:
            return instrument_type
    return None


def _parse_weight_pct(raw: Any) -> float | None:
    if isinstance(raw, (int, float)):
        return float(raw) * 100
    if isinstance(raw, str) and raw.strip().startswith("$"):
        # The AMC's own materiality footnote: "$ Less Than 0.01% of Net
        # Asset Value" -- a real, confirmed convention, not a parse
        # failure dressed up as zero.
        return 0.0
    return None


def _parse_pct_fraction(raw: Any) -> float | None:
    if isinstance(raw, (int, float)):
        return float(raw) * 100
    return None
