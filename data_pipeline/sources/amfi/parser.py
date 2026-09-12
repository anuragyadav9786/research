"""Parser for AMFI's NAVAll.txt format.

File shape (semicolon-delimited, documented public structure — not fund
data itself):

    Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;Net Asset Value;Date

    Open Ended Schemes(Debt Scheme - Overnight Fund)

    Aditya Birla Sun Life Mutual Fund
    118551;INF209K01UN8;-;Some Scheme - Direct Plan - Growth;1234.5678;12-Sep-2026
    118552;INF209K01UM0;-;Some Scheme - Regular Plan - Growth;1230.1234;12-Sep-2026

    Open Ended Schemes(Debt Scheme - Liquid Fund)

    Aditya Birla Sun Life Mutual Fund
    ...

Section header lines (no ';') alternate between "Open/Close Ended/Interval
Fund Schemes(<category>)" category markers and AMC name lines; every
semicolon-delimited row inherits whichever of each it most recently saw.
This parser only extracts structure — it does not interpret NAV values or
validate them (see `data_pipeline/validation/nav_validation.py` for that).
"""
from __future__ import annotations

from dataclasses import dataclass

_CATEGORY_PREFIXES = (
    "Open Ended Schemes(",
    "Close Ended Schemes(",
    "Interval Fund Schemes(",
)


@dataclass
class RawNavRecord:
    scheme_code: str
    isin_growth: str | None
    isin_div_reinvestment: str | None
    scheme_name: str
    nav_raw: str
    date_raw: str
    amc_name: str | None
    category: str | None
    line_number: int


def _clean_isin(value: str) -> str | None:
    value = value.strip()
    return None if value in ("", "-") else value


def parse_navall(raw_text: str) -> list[RawNavRecord]:
    """Parse NAVAll.txt content into a flat list of RawNavRecord.

    Deliberately permissive about structure (blank lines, missing trailing
    fields) since AMFI's own file has historically had minor formatting
    inconsistencies — but never permissive about the data fields themselves,
    which are validated separately.
    """
    records: list[RawNavRecord] = []
    current_amc: str | None = None
    current_category: str | None = None

    for line_number, raw_line in enumerate(raw_text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue

        if ";" not in line:
            if line.startswith(_CATEGORY_PREFIXES):
                current_category = line
            elif not line.lower().startswith("scheme code"):
                current_amc = line
            continue

        if line.lower().startswith("scheme code;"):
            continue  # column header row

        fields = line.split(";")
        # Pad short rows rather than silently dropping them — a malformed
        # row still needs to be counted and rejected with a clear reason by
        # the validator, not made to vanish invisibly from the run's totals.
        fields = (fields + [""] * 6)[:6]

        scheme_code, isin_growth, isin_div, scheme_name, nav_raw, date_raw = (
            f.strip() for f in fields
        )
        records.append(
            RawNavRecord(
                scheme_code=scheme_code,
                isin_growth=_clean_isin(isin_growth),
                isin_div_reinvestment=_clean_isin(isin_div),
                scheme_name=scheme_name,
                nav_raw=nav_raw,
                date_raw=date_raw,
                amc_name=current_amc,
                category=current_category,
                line_number=line_number,
            )
        )

    return records
