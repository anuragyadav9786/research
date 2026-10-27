"""Reads AMC configuration from the AMC_Directory sheet and reads/writes
run results in the Monthly_Tracker sheet — both tabs of the same master
catalog spreadsheet (config.CATALOG_SPREADSHEET_ID).

Column access is by header name throughout, not fixed column letters/
indices, so reordering a column in the sheet doesn't silently break
this — gspread's get_all_records() already returns each row as a
{header: value} dict for exactly this reason.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass

import gspread

import config


@dataclass
class AMCConfig:
    amc_name: str
    short_code: str
    official_website: str
    disclosure_url: str
    file_format: str
    reporting_schedule: str


def _is_real_amc_row(row: dict) -> bool:
    """An AMC_Directory row counts as a real, active AMC only if it has
    both a non-blank AMC Name and Short Code — a blank/error/log row
    (e.g. a stray note row mixed into the sheet) naturally has at least
    one of these empty and is skipped, rather than relying on a specific
    hardcoded row number that would stop working the moment the sheet's
    layout shifts."""
    return bool(str(row.get("AMC Name", "")).strip()) and bool(str(row.get("Short Code", "")).strip())


class TrackerManager:
    def __init__(self, credentials):
        self._gc = gspread.authorize(credentials)
        self._spreadsheet = self._gc.open_by_key(config.CATALOG_SPREADSHEET_ID)

    def _amc_directory_sheet(self):
        return self._spreadsheet.worksheet(config.AMC_DIRECTORY_SHEET_NAME)

    def _monthly_tracker_sheet(self):
        return self._spreadsheet.worksheet(config.MONTHLY_TRACKER_SHEET_NAME)

    def get_amc_directory(self) -> list[AMCConfig]:
        """Every real, active AMC row from AMC_Directory. Short Code is
        upper-cased for a consistent join key against the scraper
        registries (scrapers/tier1_direct.py, scrapers/tier2_playwright.py
        key on upper-case short codes)."""
        rows = self._amc_directory_sheet().get_all_records()
        return [
            AMCConfig(
                amc_name=str(row.get("AMC Name", "")).strip(),
                short_code=str(row.get("Short Code", "")).strip().upper(),
                official_website=str(row.get("Official Website", "")).strip(),
                disclosure_url=str(row.get("Monthly Portfolio Disclosure URL", "")).strip(),
                file_format=str(row.get("File Format", "")).strip(),
                reporting_schedule=str(row.get("Reporting Schedule", "")).strip(),
            )
            for row in rows
            if _is_real_amc_row(row)
        ]

    def _tracker_rows_with_index(self) -> list[tuple[int, dict]]:
        """Monthly_Tracker rows paired with their real 1-indexed sheet
        row number (header is row 1, so the first data row is row 2) —
        needed for log_download_result's update-in-place path."""
        records = self._monthly_tracker_sheet().get_all_records()
        return [(i + 2, row) for i, row in enumerate(records)]

    def is_already_downloaded(self, month_year: str, short_code: str) -> bool:
        """True if Monthly_Tracker already has a row for this
        (month, AMC) pair logged as a successful download — main.py
        skips re-fetching in that case unless --force is passed."""
        for _, row in self._tracker_rows_with_index():
            if (
                str(row.get("Month-Year", "")).strip() == month_year
                and str(row.get("AMC Name", "")).strip().upper() == short_code.upper()
                and str(row.get("Supabase Sync Status", "")).strip().lower() != "failed"
            ):
                return True
        return False

    def log_download_result(
        self,
        month_year: str,
        amc_name: str,
        scheme_scope: str,
        file_name: str,
        drive_url: str,
        notes: str = "",
        sync_status: str = "Pending",
    ) -> None:
        """Appends a new Monthly_Tracker row, or updates the existing
        row in place if one already exists for this exact
        (month, AMC, file_name) — keeps a --force re-run idempotent in
        the sheet instead of accumulating duplicate rows for the same
        real file."""
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        row_values = [
            month_year,
            amc_name,
            scheme_scope,
            file_name,
            drive_url,
            now_iso,
            sync_status,
            notes,
        ]

        sheet = self._monthly_tracker_sheet()
        for row_number, row in self._tracker_rows_with_index():
            if (
                str(row.get("Month-Year", "")).strip() == month_year
                and str(row.get("AMC Name", "")).strip() == amc_name
                and str(row.get("File Name", "")).strip() == file_name
            ):
                sheet.update(f"A{row_number}:H{row_number}", [row_values])
                return

        sheet.append_row(row_values, value_input_option="USER_ENTERED")


__all__ = ["TrackerManager", "AMCConfig"]
