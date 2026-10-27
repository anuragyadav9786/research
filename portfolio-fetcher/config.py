"""Central configuration for the portfolio-fetcher worker — folder/sheet
IDs, scopes, and the SEBI reporting-month calculation, read from
environment variables with the real IDs already in use as defaults so a
local run with no env vars set still points at the right place.
"""
from __future__ import annotations

import datetime
import os

DRIVE_MASTER_DB_FOLDER_ID = os.environ.get(
    "DRIVE_MASTER_DB_FOLDER_ID", "1hSNV629OnGOchyP0coX72lVA7-Eg1kAx"
)
DRIVE_MONTHLY_PORTFOLIOS_PARENT_ID = os.environ.get(
    "DRIVE_MONTHLY_PORTFOLIOS_PARENT_ID", "1acNwjxV2mJnEZ9BDAlKoDZpZTVav9h_5"
)
CATALOG_SPREADSHEET_ID = os.environ.get(
    "CATALOG_SPREADSHEET_ID", "1sSIAhoPCMHYQH6K5kF9oOZwAp7Llbyrr8d9Db0-YCFU"
)

AMC_DIRECTORY_SHEET_NAME = "AMC_Directory"
MONTHLY_TRACKER_SHEET_NAME = "Monthly_Tracker"

# google.oauth2.credentials.Credentials scopes — "drive" (not the more
# restrictive "drive.file") since get_or_create_monthly_folder needs to
# LIST folders it didn't itself create, and "spreadsheets" for the
# AMC_Directory read + Monthly_Tracker read/write.
SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]

# Primary: a full OAuth2 user token, base64-encoded, in one env var
# (Render's env editor handles long single-line values more reliably
# than a mounted secret file across redeploys). GOOGLE_OAUTH_TOKEN_FILE
# is the local/dev alternative — a path to a token.json written by the
# one-time OAuth consent flow (see README.md).
GOOGLE_OAUTH_TOKEN_B64_ENV = "GOOGLE_OAUTH_TOKEN_B64"
GOOGLE_OAUTH_TOKEN_FILE_ENV = "GOOGLE_OAUTH_TOKEN_FILE"
DEFAULT_OAUTH_TOKEN_FILE = "token.json"

# Fallback: the existing service-account path (GOOGLE_SERVICE_ACCOUNT_JSON,
# the full downloaded key JSON as one env var) — still requires the
# destination folder to actually live inside a Google Shared Drive (see
# README.md's "Service Accounts do not have storage quota" explanation);
# supportsAllDrives=True alone does not grant quota, it only matters once
# the destination genuinely is a Shared Drive.
GOOGLE_SERVICE_ACCOUNT_JSON_ENV = "GOOGLE_SERVICE_ACCOUNT_JSON"
GOOGLE_SERVICE_ACCOUNT_FILE_ENV = "GOOGLE_SERVICE_ACCOUNT_FILE"
DEFAULT_SERVICE_ACCOUNT_FILE = "service_account.json"

XLSX_MIMETYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
XLS_MIMETYPE = "application/vnd.ms-excel"

MIN_PORTFOLIO_FILE_SIZE_BYTES = 25_000  # per spec: reject anything under 25 KB as not a real portfolio workbook


def current_reporting_month(today: datetime.date | None = None) -> str:
    """SEBI's monthly portfolio disclosure cycle: an AMC publishes month
    N's portfolio by the 10th of month N+1. A run any time in month N+1
    is therefore collecting month N's file — i.e. always the previous
    calendar month relative to `today`, regardless of which day inside
    the current month the run happens to land on (the 10th-of-month
    deadline affects when the AMC's file becomes available, not which
    month this worker should be asking for)."""
    today = today or datetime.date.today()
    first_of_this_month = today.replace(day=1)
    last_day_of_prev_month = first_of_this_month - datetime.timedelta(days=1)
    return last_day_of_prev_month.strftime("%Y-%m")
