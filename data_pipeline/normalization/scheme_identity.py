"""Pure parsing of plan/option classification out of AMFI's dedicated
Plan and Option columns (see parser.py's module docstring — these are
separate columns in the real file, not embedded in the Scheme Name).

Real Option text varies in ways this parses conservatively rather than
guessing at, all confirmed against the live file's actual vocabulary:
- Growth: "Growth Option", "GROWTH", "Growth", and "Cumulative" (a
  well-established, official mutual-fund industry synonym for Growth —
  no distribution, NAV accumulates — used especially in older debt-fund
  documentation, not an invented mapping).
- IDCW: "IDCW Option", "IDCW", "IDCW-Re-investment", "MONTHLY DCW
  Payout" (AMFI's own data uses "DCW" as a shorthand for "IDCW" in some
  payout-frequency variants), and "Income Distribution cum Capital
  Withdrawal" spelled out in full — that phrase IS what the IDCW
  abbreviation officially stands for (SEBI renamed "Dividend" to this in
  2021), so matching it is recognizing the same term AMFI itself uses,
  not guessing at a new one.
Anything this can't confidently classify as exactly one of growth/IDCW —
including a blank Plan/Option (typical of exchange-traded instruments
with no distributor-plan concept at all), "Bonus" (a real third option
type this schema doesn't model), or an ambiguous/administrative bucket
like "Unclaimed Redemption" — returns None rather than guessing, per
Rule 2 (never fabricate financial data): a wrong guess here would
misclassify a real fund's identity, not just omit a data point.
"""
from __future__ import annotations

import re

_PLAN_PATTERN = re.compile(r"\b(Direct|Regular)\b", re.IGNORECASE)
_GROWTH_PATTERN = re.compile(r"\b(Growth|Cumulative)\b", re.IGNORECASE)
_IDCW_PATTERN = re.compile(
    r"\b(IDCW|Dividend|DCW)\b|Income\s+Distribution\s+cum\s+Capital\s+Withdrawal",
    re.IGNORECASE,
)

_CATEGORY_HEADER_PATTERN = re.compile(r"\((.*)\)\s*$")


def parse_plan(plan_raw: str) -> str | None:
    """Classify a Plan column value as 'direct' or 'regular', or None if
    neither (or both) are mentioned — e.g. a blank Plan field, typical of
    ETFs and other instruments with no distributor-plan concept."""
    distinct = {p.lower() for p in _PLAN_PATTERN.findall(plan_raw)}
    if len(distinct) != 1:
        return None
    return distinct.pop()


def parse_option(option_raw: str) -> str | None:
    """Classify an Option column value as 'growth' or 'idcw' (see module
    docstring for the recognized real-world synonyms), or None if neither
    (or both) are recognizable — e.g. a blank Option field, or an option
    this schema doesn't model (like "Bonus")."""
    has_growth = bool(_GROWTH_PATTERN.search(option_raw))
    has_idcw = bool(_IDCW_PATTERN.search(option_raw))
    if has_growth == has_idcw:  # neither present, or both present — ambiguous
        return None
    return "growth" if has_growth else "idcw"


def parse_category_header(header_line: str) -> str | None:
    """Extract the category label from a NAVAll.txt section header, e.g.
    "Open Ended Schemes(Equity Scheme - Large Cap Fund)" -> "Equity Scheme
    - Large Cap Fund". Returns None if the header doesn't have the expected
    parenthesized category."""
    match = _CATEGORY_HEADER_PATTERN.search(header_line)
    if not match:
        return None
    category = match.group(1).strip()
    return category or None
