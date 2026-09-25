"""Classifies a scheme's free-text category string (Scheme.category —
either AMFI's own full header wording, e.g. "Equity Scheme - Large Cap
Fund", or this platform's simplified seed-data form, e.g. "Equity -
Large Cap") into a broad asset class and, for equity schemes, a
market-cap/style sub-category.

Classified entirely from the category string's own stated wording —
never from a scheme's disclosed holdings, its name, or any other proxy.
A category that doesn't match a known pattern is reported as
"Unclassified" rather than guessed at, per the Portfolio Analysis spec's
"never invent classifications" rule.

Rules are ordered most-specific-first (e.g. "Large & Mid Cap" checked
before the standalone "Large Cap"/"Mid Cap" patterns it would otherwise
also match) — the same convention cas_parser.py's transaction-type rules
use, for the same reason.
"""
from __future__ import annotations

import re

ASSET_CLASS_UNCLASSIFIED = "Unclassified"

_ASSET_CLASS_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bgold\b|\bsilver\b", re.IGNORECASE), "Gold"),
    (re.compile(r"^hybrid\b", re.IGNORECASE), "Hybrid"),
    (re.compile(r"^equity\b", re.IGNORECASE), "Equity"),
    (re.compile(r"^debt\b", re.IGNORECASE), "Debt"),
    # AMFI's own "Other Scheme" bucket (Index Funds/ETFs/FoFs) and
    # "Solution Oriented" (Retirement/Children's) funds are respected as
    # their own stated category, not reclassified into Equity/Hybrid by
    # guessing at their typical underlying mix.
    (re.compile(r"^other\b|index fund|\betf\b|fund of fund|\bfof\b", re.IGNORECASE), "Other"),
    (re.compile(r"^solution oriented", re.IGNORECASE), "Other"),
]

_EQUITY_STYLE_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"large\s*&?\s*mid\s*cap|large\s+and\s+mid\s*cap", re.IGNORECASE), "Large & Mid Cap"),
    (re.compile(r"large\s*cap", re.IGNORECASE), "Large Cap"),
    (re.compile(r"mid\s*cap", re.IGNORECASE), "Mid Cap"),
    (re.compile(r"small\s*cap", re.IGNORECASE), "Small Cap"),
    (re.compile(r"flexi\s*cap", re.IGNORECASE), "Flexi Cap"),
    (re.compile(r"multi\s*cap", re.IGNORECASE), "Multi Cap"),
    (re.compile(r"focused", re.IGNORECASE), "Focused"),
    (re.compile(r"dividend\s*yield", re.IGNORECASE), "Dividend Yield"),
    (re.compile(r"\bvalue\b|\bcontra\b", re.IGNORECASE), "Value"),
    (re.compile(r"\belss\b|tax\s*sav", re.IGNORECASE), "ELSS"),
    (re.compile(r"sectoral|thematic", re.IGNORECASE), "Sectoral/Thematic"),
    (re.compile(r"international|overseas|global", re.IGNORECASE), "International"),
]


def classify_asset_class(category: str) -> str:
    for pattern, asset_class in _ASSET_CLASS_RULES:
        if pattern.search(category):
            return asset_class
    return ASSET_CLASS_UNCLASSIFIED


def classify_equity_style(category: str) -> str | None:
    """Only meaningful when classify_asset_class(category) == 'Equity'
    — returns None (not "Other") for a non-equity category, since the
    question doesn't apply rather than having an unrecognized answer.
    Returns "Other" for a recognized equity scheme whose specific
    market-cap/style isn't one of the named patterns above (e.g. an
    equity category this hasn't seen the exact wording for yet)."""
    if classify_asset_class(category) != "Equity":
        return None
    for pattern, style in _EQUITY_STYLE_RULES:
        if pattern.search(category):
            return style
    return "Other"
