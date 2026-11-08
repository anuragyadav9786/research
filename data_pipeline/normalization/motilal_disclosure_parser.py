"""Parses Motilal Oswal's real monthly portfolio-disclosure workbook
(the `.xlsx` published each month, e.g.
`https://www.motilaloswalmf.com/content/dam/motilal-mf/downloads/mf/month-end-portfolio/<YYYY>/<upload-month>/<filename>.xlsx`)
into structured per-scheme holdings.

Confirmed against the real September 2026 file, not guessed: 91 sheets
(one `Index` sheet mapping Motilal's own internal fund codes, e.g. "YO08",
to scheme names, plus one sheet per scheme, 90 total). Every scheme
sheet's real holdings table occupies columns 0-6 only:

    0: Sr. No. -- NOT a reliable row-shape signal on its own: a category
       header is usually a lettered marker ("(A)", "(c)") but sometimes
       has none at all (e.g. the Silver ETF sheet's own top-level
       "SILVER" header), and a genuine holding is usually a plain
       integer but is confirmed real as None too (seen on a real REIT
       holding, the only constituent of its category). The only
       reliable discriminator, confirmed across all 90 real sheets and
       used throughout this parser, is column 5's numeric market value
       -- the same "classified purely by having a genuinely numeric
       market value, never by matching specific label text" discipline
       ABSL's own parser already relies on.
    1: Name of the Instrument
    2: ISIN
    3: "Industry*", "Industry* / Rating", or "Rating" depending on the
       sheet -- an AMFI-style equity sector for an equity row, a credit
       rating (e.g. "CRISIL A1+") for a debt/money-market row, blank for
       everything else -- confirmed against a real row of each category.
    4: Quantity
    5: Market/Fair Value, in Lakhs of rupees (so always x100000 before
       storing, same convention as ABSL's file)
    6: % to Net Assets -- ALREADY on a 0-100 scale, confirmed by checking
       the GRAND TOTAL row across 5 different real sheets (every one
       reads ~100, never 1.0) -- unlike ABSL's file, which stores this as
       a 0-1 fraction. Never multiply this by 100. Occasionally the
       string "$0.00" instead of a number, for a position whose weight
       rounds to zero (matching the sheet's own footnote, "$ Less than
       0.005%"); treated as 0.0, not a parse failure.

Column 7 ("YTM") exists only on some (debt-oriented) sheets -- confirmed
real, parsed when present. No "YTC" column exists anywhere in this file,
confirmed across all 90 real sheets -- `ytc_pct` is therefore always
`None`, a confirmed real absence, not a parser gap. Columns 7-8 are
otherwise blank spacers, and columns 9-10 sometimes hold a completely
unrelated top-sector-allocation summary table (its own, different 0-1
fraction scale) that happens to render in the same row range as the
holdings table -- this parser never reads past column 7, so that table
can never leak into a holding's data.

Category-header rows mostly use the same lettered-prefix convention as
ABSL's file ("(A)"/"(a)"/"(b)" etc.), though confirmed real exceptions
exist with no marker at all. A sub-category with no instrument-type
meaning of its own (e.g. "Privately placed / Unlisted", confirmed nested
under a Debt Instruments parent in the real file) inherits the current
state instead of resetting it, same state-machine idea as ABSL's parser.
"Net Receivables / (Payables)" is a genuine holding row (has its own
market value/weight) despite reading like a subtotal -- always stored as
a `cash_equivalent`, same bucket as TREPS, regardless of whichever
category happened to precede it; one real Arbitrage-fund sheet shows this
line at 72.35% of net assets (margin/settlement cash from short futures
positions, confirmed from the real file, not a parsing error).

Some debt instrument names carry trailing footnote-reference markers
("** #", "**") -- stripped before storing, since they're confirmed
footnote punctuation, never part of the real name.
"""
from __future__ import annotations

import io
import re
from datetime import date, datetime
from typing import Any

import openpyxl

from data_pipeline.normalization.disclosure_types import DisclosureHolding, DisclosureScheme, IndexEntry

__all__ = [
    "DisclosureHolding",
    "DisclosureScheme",
    "IndexEntry",
    "parse_disclosure_workbook",
    "parse_index_sheet",
]

INDEX_SHEET_NAME = "Index"

# Matched case-insensitively against a category-header row's own name
# text, longest/most-specific markers first so a shorter marker that's
# also a substring of a longer one never wins by accident. Every entry
# confirmed against a real header row across all 90 real scheme sheets in
# the September 2026 file. A marker mapped to `None` means "inherit the
# surrounding category's own type" -- it's a sub-heading with no
# instrument-type meaning of its own (confirmed from real nesting, not
# guessed): "Privately placed / Unlisted" sits under Debt Instruments in
# the real file the same way ABSL's "(b) Unlisted" sits under Equity.
_CATEGORY_INSTRUMENT_TYPES: list[tuple[str, str | None]] = [
    ("equity & equity related", "equity"),
    ("international exchange traded funds", "foreign_security"),
    ("exchange traded funds", "mutual_fund_unit"),
    ("mutual fund units", "mutual_fund_unit"),
    ("corporate debt market development fund", "other"),
    ("debt instruments", "debt"),
    ("money market instruments", "money_market"),
    ("treasury bill", "money_market"),
    ("certificate of deposit", "money_market"),
    ("commercial paper", "money_market"),
    ("treps / reverse repo", "cash_equivalent"),
    ("reit", "reit_invit"),
    ("gold", "other"),
    ("silver", "other"),
    ("derivatives", "other"),
    ("index / stock futures", "other"),
    ("others", "other"),
    ("privately placed / unlisted", None),
    ("listed / awaiting listing", None),
    ("unlisted", None),
]

_SECTOR_LIKE_INSTRUMENT_TYPES = {"equity", "reit_invit", "foreign_security"}
_RATING_LIKE_INSTRUMENT_TYPES = {"debt", "securitised_debt", "government_security", "money_market"}

_TRAILING_FOOTNOTE_MARKER_RE = re.compile(r"(?:\s*[*#]+)+\s*$")
_AS_OF_DATE_RE = re.compile(r"PORTFOLIO STATEMENT AS ON\s+([A-Za-z]+\s+\d{1,2},\s*\d{4})", re.IGNORECASE)
_HEADER_ROW_SEARCH_LIMIT = 15
_INTRO_SEARCH_LIMIT = 10


def parse_disclosure_workbook(file_bytes: bytes) -> list[DisclosureScheme]:
    """Every scheme sheet in the workbook, parsed. A sheet whose scheme
    name or "MONTHLY PORTFOLIO STATEMENT AS ON" date can't be found is
    skipped entirely (never guessed) -- this would mean the file's own
    layout has changed in a way this parser doesn't yet understand, not a
    normal/expected condition."""
    workbook = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    schemes: list[DisclosureScheme] = []
    for sheet_name in workbook.sheetnames:
        if sheet_name == INDEX_SHEET_NAME:
            continue
        rows = list(workbook[sheet_name].iter_rows(values_only=True))
        scheme = _parse_scheme_sheet_rows(sheet_name, rows)
        if scheme is not None:
            schemes.append(scheme)
    return schemes


def parse_index_sheet(file_bytes: bytes) -> list[IndexEntry]:
    """The `Index` sheet's own (Sr No., Fund Name, Fund Code) rows --
    Motilal's own stable fund code is the durable join key a
    scheme-identity mapping should be built against (see
    motilal_scheme_identity.py), not the full fund name, which can vary
    in wording between this file and whatever name a scheme was
    originally onboarded under."""
    workbook = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    sheet = workbook[INDEX_SHEET_NAME]
    entries: list[IndexEntry] = []
    for row in sheet.iter_rows(values_only=True):
        sr_no, name, code = (row[c] if len(row) > c else None for c in range(2, 5))
        if not isinstance(sr_no, (int, float)):
            continue
        if not (isinstance(code, str) and code.strip()) or not (isinstance(name, str) and name.strip()):
            continue
        entries.append(IndexEntry(scheme_code=str(int(sr_no)), short_code=code.strip(), scheme_name=name.strip()))
    return entries


def _parse_scheme_sheet_rows(short_code: str, rows: list[tuple[Any, ...]]) -> DisclosureScheme | None:
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
        name = row[1] if len(row) > 1 else None
        if not isinstance(name, str) or not name.strip():
            continue
        name_clean = _TRAILING_FOOTNOTE_MARKER_RE.sub("", name.strip())
        name_lower = name_clean.lower()

        if name_lower == "grand total":
            # The real holdings table definitively ends here -- everything
            # after it (footnotes, Total Expense Ratio, NAV/IDCW notes,
            # risk-o-meter) has its own unrelated layout and must never be
            # scanned for holdings. Belt-and-suspenders alongside the
            # market-value check below, which already filters this
            # content out on its own -- same defensive precedent as
            # ABSL's parser.
            break
        if name_lower in ("sub total", "total"):
            # Confirmed real: a real subtotal, never a holding or header,
            # despite itself carrying a genuinely numeric market value --
            # must be excluded by name before the market-value check
            # below, which would otherwise mistake it for a holding.
            continue

        market_value_lakhs_raw = row[5] if len(row) > 5 else None
        if not isinstance(market_value_lakhs_raw, (int, float)):
            # A category/sub-category header row -- confirmed real to
            # use either a lettered marker in Sr. No. ("(A)", "(c)") or,
            # for some sheets (e.g. the Silver ETF's own top-level
            # "SILVER" header), no marker at all. Either way, a category
            # header never carries a numeric market value, which is this
            # parser's one and only holding-row signal -- the same
            # "classified purely by having a genuinely numeric market
            # value, never by matching specific label text" discipline
            # ABSL's own parser documents and relies on.
            matched_type = _match_category_header(name_lower)
            if matched_type is not None:
                current_instrument_type = matched_type
            continue

        # "Net Receivables / (Payables)" is a cash-equivalent adjustment,
        # same bucket as TREPS, regardless of whatever category happened
        # to precede it in the sheet -- never inherited from state. A
        # genuine holding row's own Sr. No. is otherwise either a plain
        # integer or, confirmed real for at least one REIT holding seen
        # with only a single constituent, None -- Sr. No.'s shape plays
        # no part in distinguishing a holding from a header; only the
        # numeric-market-value check above does that.
        is_net_receivable_payable = name_lower.startswith("net receivable")
        holding_instrument_type = "cash_equivalent" if is_net_receivable_payable else current_instrument_type
        if holding_instrument_type is None:
            scheme.skipped_rows.append(f"{name_clean!r}: no category header seen yet")
            continue

        weight_pct = _parse_weight_pct(row[6] if len(row) > 6 else None)
        if weight_pct is None:
            scheme.skipped_rows.append(f"{name_clean!r}: unparseable % to Net Assets")
            continue

        isin_raw = row[2] if len(row) > 2 else None
        isin = isin_raw.strip() if isinstance(isin_raw, str) and isin_raw.strip() else None

        industry_or_rating_raw = row[3] if len(row) > 3 else None
        industry_or_rating = (
            industry_or_rating_raw.strip()
            if isinstance(industry_or_rating_raw, str) and industry_or_rating_raw.strip()
            else None
        )
        sector = industry_or_rating if holding_instrument_type in _SECTOR_LIKE_INSTRUMENT_TYPES else None
        credit_rating = industry_or_rating if holding_instrument_type in _RATING_LIKE_INSTRUMENT_TYPES else None

        quantity_raw = row[4] if len(row) > 4 else None
        quantity = float(quantity_raw) if isinstance(quantity_raw, (int, float)) else None

        scheme.holdings.append(
            DisclosureHolding(
                instrument_name=name_clean,
                isin=isin,
                sector=sector,
                credit_rating=credit_rating,
                quantity=quantity,
                market_value_rupees=float(market_value_lakhs_raw) * 100_000,
                weight_pct=weight_pct,
                ytm_pct=_parse_ytm(row[7] if len(row) > 7 else None),
                ytc_pct=None,
                instrument_type=holding_instrument_type,
            )
        )

    return scheme


def _extract_scheme_name(rows: list[tuple[Any, ...]]) -> str | None:
    """Every real sheet's intro is the same fixed boilerplate (AMC name/
    address/CIN, then "MONTHLY PORTFOLIO STATEMENT AS ON ..."), so the
    scheme name is reliably the first non-blank row right after that
    statement line -- never guessed from marker text, since a
    description row right after the name (e.g. "(An open ended ...)")
    could otherwise be mistaken for it."""
    statement_row_idx = None
    for i, row in enumerate(rows[:_INTRO_SEARCH_LIMIT]):
        if any(isinstance(cell, str) and "MONTHLY PORTFOLIO STATEMENT AS ON" in cell.upper() for cell in row):
            statement_row_idx = i
            break
    if statement_row_idx is None:
        return None
    for row in rows[statement_row_idx + 1 : statement_row_idx + 1 + _INTRO_SEARCH_LIMIT]:
        name = row[0] if row else None
        if isinstance(name, str) and name.strip():
            return name.strip()
    return None


def _extract_as_of_date(rows: list[tuple[Any, ...]]) -> date | None:
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


def _find_header_row(rows: list[tuple[Any, ...]]) -> int | None:
    for i, row in enumerate(rows[:_HEADER_ROW_SEARCH_LIMIT]):
        row_text = " ".join(str(c) for c in row if c is not None)
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
        return float(raw)
    if isinstance(raw, str) and raw.strip().startswith("$"):
        # The sheet's own materiality footnote ("$ Less than 0.005%") --
        # a real, confirmed convention (seen on real derivatives rows),
        # not a parse failure dressed up as zero.
        return 0.0
    return None


def _parse_ytm(raw: Any) -> float | None:
    # Confirmed from the real file: unlike the "% to Net Assets" column
    # (already a 0-100 number, never multiplied), the YTM column's cells
    # are Excel percentage-formatted -- openpyxl (even with data_only)
    # returns the underlying fraction (0.0575 for a cell displaying
    # "5.75%"), not the displayed percentage. Verified directly against
    # YO06's real rows: col G (% to Net Assets) = 9.18, col H (YTM) =
    # 0.0575 for the same holding -- two different scales in the same
    # row, so this is a real file quirk, not a guess.
    return float(raw) * 100 if isinstance(raw, (int, float)) else None
