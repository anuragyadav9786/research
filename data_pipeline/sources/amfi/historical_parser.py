"""Parser for AMFI's historical NAV report
(portal.amfiindia.com/DownloadNAVHistoryReport_Po.aspx).

Column order confirmed via a live GitHub Actions debug run against real
date ranges (see git history) — DIFFERENT from NAVAll.txt's live-snapshot
order (see amfi/parser.py's module docstring):

    Scheme Code;NAV Name;Plan;Option;ISIN Div Payout/ISIN Growth;ISIN Div Reinvestment;Net Asset Value;Date

"NAV Name" here is a compound field (the scheme name with its plan/option
suffix folded in), unlike the live endpoint's clean "Scheme Name" column —
so, unlike parser.py, this module makes no attempt to classify plan/option
or feed scheme_onboarding.py. Historical backfill only ever MATCHES rows
against scheme_variants already onboarded from the live feed (see
scheme_mapping.py) by amfi_code/ISIN — never creates new scheme identity
from this endpoint, since its NAV-Name-based identity is less precise than
the live feed's dedicated Plan/Option columns.

This endpoint's section headers (category/AMC-name lines with no ';')
also render with extra spaces around parentheses, e.g.
"Open Ended Schemes ( Money Market )" vs the live endpoint's
"Open Ended Schemes(Money Market)" — irrelevant here, since backfill only
needs scheme_code/NAV/date, so this parser doesn't attempt to extract
category or AMC name at all; every record's `amc_name`/`category` stays
None.
"""
from __future__ import annotations

from data_pipeline.sources.amfi.parser import RawNavRecord

_FIELD_COUNT = 8


def _clean_isin(value: str) -> str | None:
    value = value.strip()
    return None if value in ("", "-") else value


def parse_historical_navall(raw_text: str) -> list[RawNavRecord]:
    """Parse a historical NAV report into a flat list of RawNavRecord.

    One record per (scheme, date) row — unlike the live snapshot, the same
    scheme_code legitimately repeats once per date covered by the request.
    """
    records: list[RawNavRecord] = []

    for line_number, raw_line in enumerate(raw_text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or ";" not in line:
            continue  # blank line, or a category/AMC-name section header — not needed for backfill

        if line.lower().startswith("scheme code;"):
            continue  # column header row

        fields = line.split(";")
        fields = (fields + [""] * _FIELD_COUNT)[:_FIELD_COUNT]

        scheme_code, nav_name, plan_raw, option_raw, isin_growth, isin_div, nav_raw, date_raw = (
            f.strip() for f in fields
        )
        records.append(
            RawNavRecord(
                scheme_code=scheme_code,
                isin_growth=_clean_isin(isin_growth),
                isin_div_reinvestment=_clean_isin(isin_div),
                scheme_name=nav_name,
                plan_raw=plan_raw,
                option_raw=option_raw,
                nav_raw=nav_raw,
                date_raw=date_raw,
                amc_name=None,
                category=None,
                line_number=line_number,
            )
        )

    return records
