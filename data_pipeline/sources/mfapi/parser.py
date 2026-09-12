"""Parses api.mfapi.in's per-scheme NAV history response.

Each entry in the response body's "data" list is `{"date": "DD-MM-YYYY",
"nav": "123.45670"}` — confirmed against the real endpoint (see client.py's
module docstring); note this date format (DD-MM-YYYY) is DIFFERENT from
both of AMFI's own endpoints (which use "DD-Mon-YYYY", e.g. "12-Sep-2026").

No scheme/ISIN identity matching happens here, unlike the AMFI-file-based
parsers — the caller (lazy_nav_backfill.py) already knows exactly which
scheme_variant it's backfilling (it asked mfapi.in for that scheme's code
directly), so this only ever needs to extract clean (date, nav) points.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass
class MfApiParseResult:
    points: list[tuple[date, float]]
    skipped: int  # entries with an unparseable date, non-numeric, or non-positive NAV


def _parse_mfapi_date(date_raw: str) -> date | None:
    try:
        return datetime.strptime(date_raw, "%d-%m-%Y").date()
    except (ValueError, TypeError):
        return None


def parse_mfapi_history(body: dict) -> MfApiParseResult:
    points: list[tuple[date, float]] = []
    skipped = 0

    for entry in body.get("data", []):
        parsed_date = _parse_mfapi_date(str(entry.get("date", "")).strip())
        try:
            nav_value = float(str(entry.get("nav", "")).strip())
        except ValueError:
            nav_value = None

        if parsed_date is None or nav_value is None or nav_value <= 0:
            skipped += 1
            continue

        points.append((parsed_date, nav_value))

    return MfApiParseResult(points=points, skipped=skipped)
