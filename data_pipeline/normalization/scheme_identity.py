"""Pure parsing of AMFI scheme identity out of NAVAll.txt's flat fields.

AMFI scheme names follow a fairly consistent, but not fully standardized,
"<fund name> - <plan> Plan - <option>" pattern (e.g. "ABC Flexi Cap Fund -
Direct Plan - Growth"). This module extracts that structure conservatively:
anything it cannot confidently classify (no recognizable plan, no
recognizable option, or an option this platform's schema doesn't model —
e.g. "Bonus") returns None rather than guessing, per Rule 2 (never
fabricate financial data) — a wrong guess here would misclassify a real
fund's identity, not just omit a data point.

Exchange-traded instruments (most ETFs) and several other real scheme
types typically carry neither a plan nor a growth/IDCW option in their
name at all, since there is no distributor-plan concept for them — they
are expected to return None here and stay unclassified rather than be
forced into a plan/option pair that doesn't apply to them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_PLAN_PATTERN = re.compile(r"\b(Direct|Regular)\b", re.IGNORECASE)
_GROWTH_PATTERN = re.compile(r"\bGrowth\b", re.IGNORECASE)
_IDCW_PATTERN = re.compile(r"\b(IDCW|Dividend)\b", re.IGNORECASE)

# Words that, on their own, mark a name segment as plan/option noise to be
# stripped when reconstructing the underlying fund's base name — never used
# to invent or alter the fund name itself, only to remove segments made up
# entirely of these tokens.
_NOISE_WORDS = {
    "direct", "regular", "plan", "growth", "idcw", "dividend", "payout",
    "reinvestment", "option", "daily", "weekly", "monthly", "quarterly",
    "annual", "half", "yearly",
}

_CATEGORY_HEADER_PATTERN = re.compile(r"\((.*)\)\s*$")


@dataclass(frozen=True)
class ParsedSchemeIdentity:
    base_name: str
    plan: str  # 'direct' | 'regular'
    option: str  # 'growth' | 'idcw'


def _is_noise_segment(segment: str) -> bool:
    words = re.findall(r"[A-Za-z]+", segment)
    return bool(words) and all(w.lower() in _NOISE_WORDS for w in words)


def parse_scheme_identity(scheme_name: str) -> ParsedSchemeIdentity | None:
    """Split a scheme name into (base fund name, plan, option), or None if
    it can't be done with confidence (see module docstring)."""
    distinct_plans = {p.lower() for p in _PLAN_PATTERN.findall(scheme_name)}
    if len(distinct_plans) != 1:
        return None  # plan missing, or both "Direct" and "Regular" mentioned
    plan = distinct_plans.pop()

    has_growth = bool(_GROWTH_PATTERN.search(scheme_name))
    has_idcw = bool(_IDCW_PATTERN.search(scheme_name))
    if has_growth == has_idcw:  # neither present, or both present — ambiguous
        return None
    option = "growth" if has_growth else "idcw"

    segments = re.split(r"\s*-\s*", scheme_name)
    base_segments = [seg.strip() for seg in segments if seg.strip() and not _is_noise_segment(seg)]
    base_name = " - ".join(base_segments).strip()
    if not base_name:
        return None

    return ParsedSchemeIdentity(base_name=base_name, plan=plan, option=option)


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
