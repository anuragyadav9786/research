"""Validation rules for parsed AMFI NAV records.

Enforces Section 19's requirements: never let missing values, invalid
dates, negative/zero NAV, or duplicate records reach the database. Every
rejected record carries a specific reason so the ingestion log can report
*why* records were dropped, not just how many.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from data_pipeline.sources.amfi.parser import RawNavRecord


@dataclass
class ValidatedNavRecord:
    scheme_code: str
    isin_growth: str | None
    isin_div_reinvestment: str | None
    scheme_name: str
    nav: float
    nav_date: date


@dataclass
class RejectedRecord:
    raw: RawNavRecord
    reason: str


@dataclass
class ValidationResult:
    accepted: list[ValidatedNavRecord] = field(default_factory=list)
    rejected: list[RejectedRecord] = field(default_factory=list)


def _parse_amfi_date(date_raw: str) -> date | None:
    # AMFI's published date format, e.g. "12-Sep-2026".
    try:
        return datetime.strptime(date_raw, "%d-%b-%Y").date()
    except (ValueError, TypeError):
        return None


def validate_navall_records(records: list[RawNavRecord]) -> ValidationResult:
    result = ValidationResult()
    seen_scheme_codes: set[str] = set()

    for rec in records:
        if not rec.scheme_code:
            result.rejected.append(RejectedRecord(rec, "missing_scheme_code"))
            continue
        if not rec.scheme_name:
            result.rejected.append(RejectedRecord(rec, "missing_scheme_name"))
            continue
        if not rec.nav_raw or not rec.date_raw:
            result.rejected.append(RejectedRecord(rec, "missing_nav_or_date"))
            continue

        if rec.scheme_code in seen_scheme_codes:
            result.rejected.append(RejectedRecord(rec, "duplicate_in_batch"))
            continue

        if rec.nav_raw.strip().upper() in ("N.A.", "NA", "-"):
            result.rejected.append(RejectedRecord(rec, "nav_not_available"))
            continue

        try:
            nav_value = float(rec.nav_raw)
        except ValueError:
            result.rejected.append(RejectedRecord(rec, "invalid_nav_format"))
            continue

        if nav_value <= 0:
            result.rejected.append(RejectedRecord(rec, "non_positive_nav"))
            continue

        nav_date = _parse_amfi_date(rec.date_raw)
        if nav_date is None:
            result.rejected.append(RejectedRecord(rec, "invalid_date_format"))
            continue

        seen_scheme_codes.add(rec.scheme_code)
        result.accepted.append(
            ValidatedNavRecord(
                scheme_code=rec.scheme_code,
                isin_growth=rec.isin_growth,
                isin_div_reinvestment=rec.isin_div_reinvestment,
                scheme_name=rec.scheme_name,
                nav=nav_value,
                nav_date=nav_date,
            )
        )

    return result
