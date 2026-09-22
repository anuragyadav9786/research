"""Parses a CAMS/KFintech Consolidated Account Statement's extracted text
into currently-held mutual fund positions.

Format confirmed by directly inspecting a real CAS PDF's rendered pages
(CAMS + KFintech co-branded "Consolidated Account Statement" header) —
not guessed. Each folio is a block starting with "Folio No: <folio> ...
PAN: <pan> ... KYC: ...", followed by a scheme description line
("<code>-<Scheme Name> - <Plan> - <Option> (Non Demat) - ISIN: <isin>
(Advisor: ...)"), a full transaction history, and a closing summary line
("Closing Unit Balance: <units> ... NAV on <date>: INR <nav> ... Total
Cost Value: <cost> ... Market Value on <date>: INR <value>"). A CAS lists
every historical transaction, not just current holdings — a folio fully
redeemed shows Closing Unit Balance: 0.000 — so only folios with a
positive closing balance represent something actually still held; every
other folio is intentionally excluded here, not just deprioritized.

Matching a parsed holding to this platform's own fund catalog is a
separate step (cas_service.py) — this module only extracts what the
statement itself states (ISIN, closing units, market value), never
guesses or fuzzy-matches a scheme name.

Known limitation, not papered over: this has been verified against one
real captured sample. A CAS-generating RTA whose exact line wording
differs enough to miss these regexes would (correctly) surface as "no
holdings found" rather than a wrong number — see cas_pdf.py's
CASUnreadableError for the sibling case of a PDF with no text layer at
all.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

_FOLIO_SPLIT_RE = re.compile(r"(?=Folio\s*No\s*:)")
_FOLIO_NO_RE = re.compile(r"Folio\s*No\s*:\s*([\w]+\s*/\s*[\w]+)")
_ISIN_LINE_RE = re.compile(r"^(.*?ISIN\s*:\s*[A-Z0-9]{12}.*)$", re.MULTILINE)
_ISIN_RE = re.compile(r"ISIN\s*:\s*([A-Z0-9]{12})")
_CLOSING_UNITS_RE = re.compile(r"Closing\s*Unit\s*Balance\s*:\s*([\d,]+\.\d+)")
_MARKET_VALUE_RE = re.compile(r"Market\s*Value\s*on\s*([\d\-A-Za-z]+)\s*:\s*INR\s*([\d,]+\.\d+)")
_STATEMENT_END_DATE_RE = re.compile(r"\d{2}-\w{3}-\d{4}\s+To\s+(\d{2}-\w{3}-\d{4})")


@dataclass
class ParsedHolding:
    isin: str
    scheme_name: str
    folio_no: str | None
    closing_units: float
    market_value: float


def _parse_amount(raw: str) -> float:
    return float(raw.replace(",", ""))


def _parse_cas_date(raw: str) -> date | None:
    try:
        return datetime.strptime(raw.strip(), "%d-%b-%Y").date()
    except ValueError:
        return None


def _extract_scheme_name(block: str) -> str:
    """Best-effort display name for the scheme line preceding " - ISIN:"
    — e.g. "189FXRGG-Bajaj Finserv Flexi Cap Fund - Regular Plan - Growth
    (Non Demat) - ISIN: ..." -> "Bajaj Finserv Flexi Cap Fund - Regular
    Plan - Growth (Non Demat)". Only used for display/debugging; matching
    a holding to this platform's own catalog is always by ISIN, never by
    this string, so an imperfect trim here never affects correctness."""
    match = _ISIN_LINE_RE.search(block)
    if not match:
        return ""
    line = match.group(1)
    before_isin = re.split(r"-\s*ISIN\s*:", line, maxsplit=1)[0].strip()
    # Drop the leading "<AMC scheme code>-" prefix, if present.
    return re.sub(r"^\S*?-", "", before_isin, count=1).strip()


def statement_end_date(text: str) -> date | None:
    match = _STATEMENT_END_DATE_RE.search(text)
    if not match:
        return None
    return _parse_cas_date(match.group(1))


def parse_cas_text(text: str) -> list[ParsedHolding]:
    holdings: list[ParsedHolding] = []

    for block in _FOLIO_SPLIT_RE.split(text):
        isin_match = _ISIN_RE.search(block)
        closing_match = _CLOSING_UNITS_RE.search(block)
        market_value_match = _MARKET_VALUE_RE.search(block)
        if not isin_match or not closing_match or not market_value_match:
            continue  # not a folio block (e.g. the header/portfolio-summary preamble)

        closing_units = _parse_amount(closing_match.group(1))
        if closing_units <= 0:
            continue  # fully redeemed — nothing currently held in this folio

        folio_match = _FOLIO_NO_RE.search(block)
        holdings.append(
            ParsedHolding(
                isin=isin_match.group(1),
                scheme_name=_extract_scheme_name(block),
                folio_no=folio_match.group(1).strip() if folio_match else None,
                closing_units=closing_units,
                market_value=_parse_amount(market_value_match.group(2)),
            )
        )

    return holdings
