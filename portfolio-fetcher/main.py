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
import re
import tempfile
from urllib.parse import urljoin

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


MIRAE_ASSET_BASE_URL = "https://www.miraeassetmf.co.in"


_MIRAE_TITLE_PERIOD_RE = re.compile(r"as on \d+\w*\s+([A-Za-z]+)\s+(\d{4})", re.IGNORECASE)


def _parse_mirae_title_period(title: str) -> tuple[int, int] | None:
    """Extracts the (month, year) a Mirae Asset item's Title actually
    covers, e.g. 'Portfolio Details as on 31st August 2026 for ...' ->
    (8, 2026). Deliberately NOT using the item's own PublishDate field
    for this — confirmed via a real API response that PublishDate is
    when the AMC uploaded the file (per SEBI, up to ~10 days into the
    following month), not the period it covers, so filtering on it
    would compare the wrong month entirely."""
    match = _MIRAE_TITLE_PERIOD_RE.search(title or "")
    if not match:
        return None
    month_name, year_str = match.groups()
    try:
        month_num = datetime.datetime.strptime(month_name, "%B").month
    except ValueError:
        return None
    return month_num, int(year_str)


def fetch_mirae_asset(month_str: str):
    """Mirae Asset — one of this platform's 3 real featured AMCs (Mirae
    Asset Large Cap). Confirmed real: instead of scraping
    /downloads/portfolio's static HTML (which never contains the file
    link — the page draws it client-side through a PDF-viewer widget),
    this calls the same background data API that widget itself calls,
    found by loading the page in a real headless browser (Playwright)
    and inspecting its network requests. Each item in the response is
    one scheme's current portfolio file, so a single call can return
    real files for several schemes at once — unlike PPFAS's adapter,
    which guesses at one consolidated file.

    KNOWN LIMITATION: the endpoint returned only its 10 most-recent
    items in testing, with no request body/parameters sent — no
    pagination parameter has been found yet, so this can miss the
    current month's file for some of Mirae Asset's ~35-40 schemes if
    more than 10 published in the same batch. Covering every scheme
    needs the real pagination/page-size parameter; not yet done here —
    each scheme this misses is simply absent from the results (not
    logged as its own NOT_FOUND row, since AMC_ADAPTERS tracks success/
    failure per AMC, not per scheme).
    """
    year_str, month_num_str = month_str.split("-")
    year, month_num = int(year_str), int(month_num_str)

    # Headers alone weren't enough — a real run returned ReturnCode 9999
    # ("Specified argument was out of the range of valid values...
    # SitefinityAPI.DownloadsManager.GetDownloadsData"), a .NET
    # Sitefinity CMS server error consistent with the endpoint reading
    # some server-side session state that only exists after actually
    # visiting the portfolio page first — not from any request body
    # (Playwright never captured one). So: visit the real page first (in
    # the same client, to pick up its session cookies), then reuse that
    # session for the data call, the way an actual browser tab would.
    headers = {
        "Referer": f"{MIRAE_ASSET_BASE_URL}/downloads/portfolio",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "X-Requested-With": "XMLHttpRequest",
    }

    try:
        with httpx.Client(headers=headers, timeout=30.0, follow_redirects=True) as client:
            client.get(f"{MIRAE_ASSET_BASE_URL}/downloads/portfolio")
            resp = client.post(f"{MIRAE_ASSET_BASE_URL}/AjaxService/GetDownloadsData")
    except Exception as exc:
        print(f"  Mirae Asset: GetDownloadsData request FAILED {type(exc).__name__}: {exc}")
        return []

    if resp.status_code != 200:
        print(f"  Mirae Asset: GetDownloadsData -> HTTP {resp.status_code}")
        return []

    data = resp.json() or {}
    items = data.get("Data") or []
    print(f"  Mirae Asset: GetDownloadsData returned {len(items)} item(s)")
    if not items:
        print(f"  Mirae Asset: full response for diagnosis: {data}")

    results = []
    for item in items:
        title = item.get("Title", "")
        relative_url = item.get("URL")
        period = _parse_mirae_title_period(title)
        if not relative_url or not period:
            continue
        if period != (month_num, year):
            continue

        file_url = urljoin(MIRAE_ASSET_BASE_URL, relative_url)
        scheme_hint = re.sub(r"^Portfolio Details as on .*? for\s*", "", title).strip() or "Mirae Asset"

        try:
            file_resp = httpx.get(file_url, timeout=30.0, follow_redirects=True)
        except Exception as exc:
            print(f"  Mirae Asset: {file_url} -> FAILED {type(exc).__name__}: {exc}")
            continue
        if file_resp.status_code != 200 or len(file_resp.content) < 1_000:
            print(f"  Mirae Asset: {file_url} -> HTTP {file_resp.status_code}")
            continue

        extension = os.path.splitext(relative_url)[1] or ".xlsx"
        mimetype = XLS_MIMETYPE if extension.lower() == ".xls" else XLSX_MIMETYPE
        file_name = f"MiraeAsset_{scheme_hint.replace(' ', '_')}_{month_str}{extension}"
        print(f"  Mirae Asset: found real file for {scheme_hint!r} at {file_url} ({len(file_resp.content)} bytes)")
        results.append((file_resp.content, file_name, mimetype, scheme_hint))

    if not results:
        print(f"  Mirae Asset: no files matched {month_str} among {len(items)} returned item(s) — needs manual confirmation (may be a pagination gap, see docstring)")

    return results


AMC_ADAPTERS = {
    "PPFAS": fetch_ppfas,
    "Mirae Asset": fetch_mirae_asset,
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
