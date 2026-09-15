"""Monthly worker: fetches AMC portfolio-disclosure Excel files and
stores them in Google Drive, logging each attempt (success or failure)
to the master catalog sheet.

Run manually with: python main.py [--month YYYY-MM]
(defaults to the previous calendar month, matching the scheduled run.)
"""
import argparse
import datetime
import json
import os
import tempfile

import httpx
import gspread
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

DRIVE_MONTHLY_FOLDER_ID = os.environ.get("DRIVE_MONTHLY_FOLDER_ID", "1acNwjxV2mJnEZ9BDAlKoDZpZTVav9h_5")
MASTER_CATALOG_SHEET_ID = os.environ.get("MASTER_CATALOG_SHEET_ID", "1sSIAhoPCMHYQH6K5kF9oOZwAp7Llbyrr8d9Db0-YCFU")

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]

XLSX_MIMETYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
XLS_MIMETYPE = "application/vnd.ms-excel"


def get_credentials():
    """Loads the service account from the GOOGLE_SERVICE_ACCOUNT_JSON env
    var — the full JSON key content, not a file path (see README.md for
    how to set this in Render)."""
    service_account_info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    return service_account.Credentials.from_service_account_info(service_account_info, scopes=SCOPES)


def get_or_create_month_folder(drive_service, month_str: str) -> str:
    """Finds or creates a folder named '<YYYY-MM> Portfolios' inside the
    monthly-portfolios parent folder. Exact-name match (not `contains`,
    which the original draft used) so "2026-08" never accidentally
    matches a differently-named folder that happens to contain that
    substring."""
    folder_name = f"{month_str} Portfolios"
    query = (
        f"'{DRIVE_MONTHLY_FOLDER_ID}' in parents and name = '{folder_name}' "
        "and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    )
    results = drive_service.files().list(
        q=query, fields="files(id, name)", supportsAllDrives=True, includeItemsFromAllDrives=True
    ).execute()
    files = results.get("files", [])
    if files:
        return files[0]["id"]

    metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [DRIVE_MONTHLY_FOLDER_ID],
    }
    folder = drive_service.files().create(body=metadata, fields="id", supportsAllDrives=True).execute()
    return folder["id"]


def upload_file_to_drive(drive_service, file_bytes: bytes, file_name: str, folder_id: str, mimetype: str):
    """Uploads a file to Drive and returns (file_id, webViewLink).

    Deliberately does NOT grant "anyone with the link can view" — the
    service account already has direct Drive API access for ingestion,
    and these are the user's own private files. The original draft's
    `permissions().create(..., {"type": "anyone", "role": "reader"})`
    call is dropped; add it back explicitly if public links are ever
    actually needed for a specific use case."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file_name)[1]) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name
    try:
        media = MediaFileUpload(tmp_path, mimetype=mimetype)
        file_metadata = {"name": file_name, "parents": [folder_id]}
        uploaded = drive_service.files().create(
            body=file_metadata, media_body=media, fields="id, webViewLink", supportsAllDrives=True
        ).execute()
        return uploaded["id"], uploaded.get("webViewLink")
    finally:
        os.remove(tmp_path)


# ---------------------------------------------------------------------------
# Per-AMC adapters. Each adapter is a function(month_str: "YYYY-MM") ->
# list of (file_bytes, file_name, mimetype, scheme_hint) tuples — one
# entry per real file found for that AMC this month. Add one function
# per AMC as they're brought online; register it in AMC_ADAPTERS below.
# ---------------------------------------------------------------------------

def fetch_ppfas(month_str: str):
    """PPFAS (Parag Parikh) — confirmed real: a consolidated workbook,
    one sheet per scheme, with genuine holdings rows (instrument name,
    ISIN, industry/rating, quantity, market value, % of net assets).

    KNOWN LIMITATION: the disclosure page only reveals the current
    month's real download link via client-side JavaScript — a plain
    HTTP GET (what this worker does) can't see it. This function
    guesses the URL from PPFAS's known naming pattern
    (PPFAS_Monthly_Portfolio_Report_<Month>_<day>_<year>.xls, dated to
    the month's last calendar day) rather than actually discovering it,
    so it WILL sometimes fail — e.g. if the real "as on" date isn't the
    last calendar day (a market holiday), or PPFAS changes the pattern.
    A failure here is expected some months, not a bug; it's logged to
    the catalog sheet as NOT_FOUND rather than silently skipped, so it
    surfaces for a manual check. Fetching the actual page with a
    headless browser (e.g. Playwright) instead of a plain GET would
    resolve this properly — not yet done here to keep this worker's
    dependencies (and Render plan requirements) minimal.
    """
    year_str, month_num_str = month_str.split("-")
    year, month_num = int(year_str), int(month_num_str)
    next_month = datetime.date(year, month_num, 28) + datetime.timedelta(days=4)
    last_day = next_month - datetime.timedelta(days=next_month.day)

    # Try the exact last calendar day, then a few days back, in case the
    # real "as on" date was an earlier business day (weekend/holiday).
    candidates = [last_day - datetime.timedelta(days=offset) for offset in range(0, 4)]

    for day in candidates:
        url = (
            f"https://amc.ppfas.com/downloads/portfolio-disclosure/{year}/"
            f"PPFAS_Monthly_Portfolio_Report_{day.strftime('%B')}_{day.day}_{year}.xls"
        )
        try:
            resp = httpx.get(url, timeout=30.0, follow_redirects=True)
        except Exception as exc:
            print(f"  PPFAS: {url} -> FAILED {type(exc).__name__}: {exc}")
            continue
        if resp.status_code == 200 and len(resp.content) > 10_000:
            print(f"  PPFAS: found real file at {url} ({len(resp.content)} bytes)")
            return [(resp.content, f"PPFAS_{month_str}.xls", XLSX_MIMETYPE, "PPFAS")]
        print(f"  PPFAS: {url} -> HTTP {resp.status_code}")

    print(f"  PPFAS: no file found for {month_str} after {len(candidates)} date guesses — needs manual confirmation")
    return []


AMC_ADAPTERS = {
    "PPFAS": fetch_ppfas,
    # Add more AMCs here as they're onboarded — see docs/data-sources.md.
}


def append_to_catalog(sheet, rows):
    if rows:
        sheet.append_rows(rows, value_input_option="USER_ENTERED")


def run(month_str: str):
    print(f"Starting portfolio fetch for cycle: {month_str}")

    credentials = get_credentials()
    drive_service = build("drive", "v3", credentials=credentials)
    month_folder_id = get_or_create_month_folder(drive_service, month_str)
    print(f"Target Drive folder: {month_folder_id}")

    gc = gspread.authorize(credentials)
    catalog_sheet = gc.open_by_key(MASTER_CATALOG_SHEET_ID).sheet1

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    catalog_rows = []

    for amc_name, fetch_fn in AMC_ADAPTERS.items():
        print(f"-- {amc_name} --")
        try:
            results = fetch_fn(month_str)
        except Exception as exc:
            print(f"{amc_name}: adapter raised {type(exc).__name__}: {exc}")
            catalog_rows.append([month_str, amc_name, "", "FAILED", str(exc), now_iso])
            continue

        if not results:
            catalog_rows.append([month_str, amc_name, "", "NOT_FOUND", "", now_iso])
            continue

        for file_bytes, file_name, mimetype, scheme_hint in results:
            try:
                file_id, view_link = upload_file_to_drive(
                    drive_service, file_bytes, file_name, month_folder_id, mimetype
                )
                print(f"{amc_name}: uploaded {file_name} ({file_id})")
                catalog_rows.append([month_str, amc_name, scheme_hint, "OK", view_link or file_id, now_iso])
            except Exception as exc:
                print(f"{amc_name}: upload FAILED {type(exc).__name__}: {exc}")
                catalog_rows.append([month_str, amc_name, scheme_hint, "UPLOAD_FAILED", str(exc), now_iso])

    append_to_catalog(catalog_sheet, catalog_rows)
    print(f"Done. {len(catalog_rows)} row(s) logged to the master catalog.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--month",
        help="Target month as YYYY-MM. Defaults to the previous calendar month "
        "(portfolios published in month N cover month N-1).",
    )
    args = parser.parse_args()

    if args.month:
        target_month = args.month
    else:
        first_of_this_month = datetime.date.today().replace(day=1)
        prev_month_date = first_of_this_month - datetime.timedelta(days=1)
        target_month = prev_month_date.strftime("%Y-%m")

    run(target_month)
