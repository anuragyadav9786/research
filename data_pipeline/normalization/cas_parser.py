"""Parses a CAMS/KFintech Consolidated Account Statement's extracted text
into both currently-held positions and the full transaction ledger.

Format confirmed by directly inspecting a real CAS PDF's rendered pages
(CAMS + KFintech co-branded "Consolidated Account Statement" header) —
not guessed. Each folio is a block starting with "Folio No: <folio> ...
PAN: <pan> ... KYC: ...", followed by a scheme description line
("<code>-<Scheme Name> - <Plan> - <Option> (Non Demat) - ISIN: <isin>
(Advisor: ...)"), a dated transaction history, and a closing summary line
("Closing Unit Balance: <units> ... NAV on <date>: INR <nav> ... Total
Cost Value: <cost> ... Market Value on <date>: INR <value>").

Every dated row within a folio's block is one of three kinds, confirmed
against the real sample:
1. A real transaction: "<date>   <description...>   <amount>   <units>
   <price>   <balance>" — always exactly 4 trailing numeric fields.
2. A charge/fee annotation tied to the transaction above it, e.g.
   "<date>   *** Stamp Duty ***   <amount>" — exactly 1 trailing numeric
   field, no units. Never a unit-bearing cash flow in its own right (the
   stamp duty/STT is a small deduction already reflected in the adjacent
   transaction's stated Amount, which is what actually bought/sold
   units) — excluded from the transaction ledger, not double-counted.
3. A pure status annotation, e.g. "<date>   ***SIPRegistered***" or
   "<date>   ***Address Updated from KRA Data***" — 0 trailing numeric
   fields. Excluded.
A row that wraps onto a second physical line (e.g. "...via MFCentral ,"
followed by "              less STT" with no leading date) contributes no
additional numbers — the transaction's own numbers are always on its
first, dated line — so continuation lines are simply not date-anchored
and never matched.

Matching a parsed holding/transaction to this platform's own fund
catalog is a separate step (cas_service.py) — this module only extracts
what the statement itself states, never guesses or fuzzy-matches a
scheme name.

Known limitation, not papered over: this has been verified against one
real captured sample. A CAS-generating RTA whose exact line wording
differs enough to miss these regexes would (correctly) surface as "no
holdings/transactions found" rather than a wrong number — see
cas_pdf.py's CASUnreadableError for the sibling case of a PDF with no
text layer at all.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime

_FOLIO_SPLIT_RE = re.compile(r"(?=Folio\s*No\s*:)")
_FOLIO_NO_RE = re.compile(r"Folio\s*No\s*:\s*([\w]+\s*/\s*[\w]+)")
_ISIN_LINE_RE = re.compile(r"^(.*?ISIN\s*:\s*[A-Z0-9]{12}.*)$", re.MULTILINE)
_ISIN_RE = re.compile(r"ISIN\s*:\s*([A-Z0-9]{12})")
_CLOSING_UNITS_RE = re.compile(r"Closing\s*Unit\s*Balance\s*:\s*([\d,]+\.\d+)")
_MARKET_VALUE_RE = re.compile(r"Market\s*Value\s*on\s*([\d\-A-Za-z]+)\s*:\s*INR\s*([\d,]+\.\d+)")
_STATEMENT_END_DATE_RE = re.compile(r"\d{2}-\w{3}-\d{4}\s+To\s+(\d{2}-\w{3}-\d{4})")

# A transaction row's own line always starts with a date; a continuation
# line (wrapped description text) never does, so this alone separates
# "a dated row to examine" from "extra text belonging to the row above."
_DATED_LINE_RE = re.compile(r"^(\d{1,2}-[A-Za-z]{3}-\d{4})\s+(.*)$")
# A monetary/unit figure always carries a decimal point in this format
# (e.g. "38.129", "5,865.98", "(492.017)") — this is what keeps an
# embedded reference/folio number in a transaction's free-text
# description (e.g. "F.No:477285782816", "CITIN25518146696", both
# integer-only) from ever being mistaken for one of the row's own
# amount/units/price/balance fields.
_NUMBER_RE = re.compile(r"\(?-?[\d,]+\.\d+\)?")

# Ordered, most-specific-first: "Lateral Shift" must be checked before a
# generic "Switch" pattern would ever apply (it doesn't currently, but
# keeps future rules safe), and "NFO Purchase"/"Sys. Investment" before
# a bare "Purchase" pattern would also match them.
_TRANSACTION_TYPE_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^Sys\.?\s*Investment", re.IGNORECASE), "SIP"),
    (re.compile(r"^Lateral\s*Shift\s*In", re.IGNORECASE), "SWITCH_IN"),
    (re.compile(r"^Lateral\s*Shift\s*Out", re.IGNORECASE), "SWITCH_OUT"),
    (re.compile(r"^Switch\s*In", re.IGNORECASE), "SWITCH_IN"),
    (re.compile(r"^Switch\s*Out", re.IGNORECASE), "SWITCH_OUT"),
    (re.compile(r"^STP\s*In", re.IGNORECASE), "STP_IN"),
    (re.compile(r"^STP\s*Out", re.IGNORECASE), "STP_OUT"),
    (re.compile(r"^SWP", re.IGNORECASE), "SWP"),
    (re.compile(r"Dividend\s*Reinvest", re.IGNORECASE), "DIVIDEND_REINVESTMENT"),
    (re.compile(r"Dividend", re.IGNORECASE), "DIVIDEND"),
    (re.compile(r"^Bonus", re.IGNORECASE), "BONUS"),
    (re.compile(r"^Reversal", re.IGNORECASE), "REVERSAL"),
    (re.compile(r"^(NFO\s*-?\s*)?Purchase", re.IGNORECASE), "PURCHASE"),
    (re.compile(r"^Redemption", re.IGNORECASE), "REDEMPTION"),
]


@dataclass
class ParsedHolding:
    isin: str
    scheme_name: str
    folio_no: str | None
    closing_units: float
    market_value: float


@dataclass
class CASTransaction:
    isin: str
    scheme_name: str
    folio_no: str | None
    transaction_date: date
    transaction_type: str  # see _TRANSACTION_TYPE_RULES; "OTHER" if none match
    description: str  # raw text, kept verbatim for transparency/debugging
    amount: float  # CAS's own sign: positive = units bought, negative (shown in parens) = units sold
    units: float  # same sign convention as amount
    price: float | None  # NAV per unit at this transaction, if stated


@dataclass
class CASParseResult:
    holdings: list[ParsedHolding] = field(default_factory=list)
    transactions: list[CASTransaction] = field(default_factory=list)


def _parse_amount(raw: str) -> float:
    return float(raw.replace(",", ""))


def _parse_signed_number(raw: str) -> float:
    """"(492.017)" -> -492.017, "5,865.98" -> 5865.98."""
    negative = raw.startswith("(") and raw.endswith(")")
    value = float(raw.strip("()").replace(",", ""))
    return -value if negative else value


def _parse_cas_date(raw: str) -> date | None:
    try:
        return datetime.strptime(raw.strip(), "%d-%b-%Y").date()
    except ValueError:
        return None


def _classify_transaction_type(description: str) -> str:
    for pattern, txn_type in _TRANSACTION_TYPE_RULES:
        if pattern.search(description):
            return txn_type
    return "OTHER"


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


def _parse_transactions_in_block(block: str, isin: str, scheme_name: str, folio_no: str | None) -> list[CASTransaction]:
    transactions: list[CASTransaction] = []
    for line in block.splitlines():
        dated = _DATED_LINE_RE.match(line)
        if not dated:
            continue  # a continuation line, or a label line like "Closing Unit Balance: ..."
        txn_date = _parse_cas_date(dated.group(1))
        if txn_date is None:
            continue
        rest = dated.group(2)
        numbers = _NUMBER_RE.findall(rest)
        if len(numbers) != 4:
            continue  # 0 numbers: pure status annotation. 1 number: a fee/charge line, not its own cash flow.
        description = rest[: rest.find(numbers[0])].strip()
        amount, units, price_raw, _balance = numbers
        transactions.append(
            CASTransaction(
                isin=isin,
                scheme_name=scheme_name,
                folio_no=folio_no,
                transaction_date=txn_date,
                transaction_type=_classify_transaction_type(description),
                description=description,
                amount=_parse_signed_number(amount),
                units=_parse_signed_number(units),
                price=_parse_signed_number(price_raw) if price_raw.strip("()") else None,
            )
        )
    return transactions


def statement_end_date(text: str) -> date | None:
    match = _STATEMENT_END_DATE_RE.search(text)
    if not match:
        return None
    return _parse_cas_date(match.group(1))


def parse_cas_text(text: str) -> CASParseResult:
    result = CASParseResult()

    for block in _FOLIO_SPLIT_RE.split(text):
        isin_match = _ISIN_RE.search(block)
        closing_match = _CLOSING_UNITS_RE.search(block)
        market_value_match = _MARKET_VALUE_RE.search(block)
        if not isin_match or not closing_match or not market_value_match:
            continue  # not a folio block (e.g. the header/portfolio-summary preamble)

        isin = isin_match.group(1)
        scheme_name = _extract_scheme_name(block)
        folio_match = _FOLIO_NO_RE.search(block)
        folio_no = folio_match.group(1).strip() if folio_match else None

        result.transactions.extend(_parse_transactions_in_block(block, isin, scheme_name, folio_no))

        closing_units = _parse_amount(closing_match.group(1))
        if closing_units <= 0:
            continue  # fully redeemed — nothing currently held in this folio

        result.holdings.append(
            ParsedHolding(
                isin=isin,
                scheme_name=scheme_name,
                folio_no=folio_no,
                closing_units=closing_units,
                market_value=_parse_amount(market_value_match.group(2)),
            )
        )

    return result
