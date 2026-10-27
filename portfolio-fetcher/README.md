# Portfolio Fetcher

A scheduled worker that fetches AMC monthly portfolio-disclosure Excel
files and stores them in Google Drive, logging every attempt to the
`Monthly_Tracker` tab of the master catalog Google Sheet. This is the
*collection* half of the pipeline — a separate ingestion job (in
`backend/`) reads from Drive and turns these files into structured
`PortfolioHolding` rows; this worker never touches the database.

## Structure

| File | Purpose |
|---|---|
| `config.py` | Folder/sheet IDs, scopes, SEBI reporting-month calculation |
| `drive_manager.py` | Dual-auth `DriveManager` — see "Why dual authentication" below |
| `tracker.py` | Reads `AMC_Directory`, reads/writes `Monthly_Tracker` |
| `scrapers/base_scraper.py` | `BaseScraper` contract + file validation (magic bytes, size, ZIP unwrap) |
| `scrapers/tier1_direct.py` | Plain-HTTP AMC adapters (PPFAS confirmed; others stubbed — see below) |
| `scrapers/tier2_playwright.py` | Dynamic-page AMC adapters (Mirae Asset confirmed; others stubbed) |
| `main.py` | CLI orchestrator |

## Why dual authentication

The real failure this fixes: a plain Google Cloud **service account** has
**zero storage quota** of its own. Uploading a *new* file with one always
fails —

```
HttpError 403 ... "Service Accounts do not have storage quota.
Leverage shared drives or user OAuth"
```

— unless the destination folder genuinely lives inside a Google
**Shared Drive** (Workspace-only), where storage belongs to the Shared
Drive itself. `supportsAllDrives=True`/`includeItemsFromAllDrives=True`
on every Drive call (already present in this code) are *necessary* for
that to work, but not *sufficient* — they don't grant quota by
themselves; they only matter once the destination really is a Shared
Drive.

`drive_manager.get_credentials()` now tries, in order:

1. **User OAuth2** (`GOOGLE_OAUTH_TOKEN_B64`, or local `token.json`) —
   the file is owned by a real Google account's own quota, so this works
   against an ordinary "My Drive" folder with no Shared Drive setup
   required at all. **Preferred.**
2. **Service account** (`GOOGLE_SERVICE_ACCOUNT_JSON`, or local
   `service_account.json`) — still requires the Shared Drive move below.
   Kept as a fallback for anyone who has already done that.

### Generating the OAuth2 token (one-time, local)

1. [Google Cloud Console](https://console.cloud.google.com/) → **APIs &
   Services → Library** → enable **Google Drive API** and **Google
   Sheets API** (if not already, from the service-account setup).
2. **APIs & Services → Credentials → Create Credentials → OAuth client
   ID** → Application type **Desktop app**. Download the resulting
   client-secret JSON.
3. Run a one-time local consent flow (not part of the deployed worker)
   with `google-auth-oauthlib` (already a `requirements.txt` dependency):

   ```python
   from google_auth_oauthlib.flow import InstalledAppFlow
   from config import SCOPES

   flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
   creds = flow.run_local_server(port=0)  # opens a browser for consent
   with open("token.json", "w") as f:
       f.write(creds.to_json())
   ```

   This signs in as **your own real Google account** — the one that
   should own the uploaded files and already has normal Drive storage.
4. For Render: base64-encode `token.json` and set it as
   `GOOGLE_OAUTH_TOKEN_B64`:
   ```bash
   base64 -w0 token.json   # macOS: base64 -i token.json
   ```
   For local runs, just set `GOOGLE_OAUTH_TOKEN_FILE=token.json` (or
   leave it as the default `./token.json`).
5. The token's `refresh_token` is long-lived; `drive_manager.py` refreshes
   the short-lived access token automatically on each run — no need to
   repeat this flow monthly.

### Fallback: service account + Shared Drive (if you'd rather keep using it)

Unchanged from before — still a valid path if you've already set this up:

1. Create a service account, enable Drive + Sheets APIs, download its
   JSON key → `GOOGLE_SERVICE_ACCOUNT_JSON`.
2. Share the Drive Master Folder (`1hSNV629OnGOchyP0coX72lVA7-Eg1kAx`)
   and the Master Catalog Sheet with the service account's email as
   **Editor**.
3. **Move the Drive folder into a real Shared Drive** — this step is
   what actually fixes the quota error for this path, not anything in
   the code:
   - Google Drive → **Shared drives** → **+ New**.
   - Add the service account's email as **Content Manager**.
   - Move the Master Folder into it (right-click → **Move to**). Folder/
     file IDs stay the same after a move.

## Updating the existing Render Cron Job

This repo's `render.yaml` documents the config a Cron Job should have —
Render's Blueprint does **not** auto-provision or update Cron Jobs, so
apply this by hand to the existing job
(`thinkfin-portfolio-fetcher`, `crn-daknidgu01pc73fpekbg`):

1. Render dashboard → the existing Cron Job → **Settings**.
2. **Runtime**: change from Python to **Docker**. **Dockerfile Path**:
   `./Dockerfile` (relative to **Root Directory**, which stays
   `portfolio-fetcher`).
3. **Schedule**: `30 20 10 * *` (02:00 AM IST on the 11th of every month).
4. **Environment** — add/update:
   - `GOOGLE_OAUTH_TOKEN_B64` — the base64 token from the setup above (preferred), **or**
   - `GOOGLE_SERVICE_ACCOUNT_JSON` — the existing fallback value, if you're keeping that path.
   - `DRIVE_MASTER_DB_FOLDER_ID` = `1hSNV629OnGOchyP0coX72lVA7-Eg1kAx`
   - `DRIVE_MONTHLY_PORTFOLIOS_PARENT_ID` = `1acNwjxV2mJnEZ9BDAlKoDZpZTVav9h_5`
   - `CATALOG_SPREADSHEET_ID` = `1sSIAhoPCMHYQH6K5kF9oOZwAp7Llbyrr8d9Db0-YCFU`
   - `HEADLESS` = `true`

## Run it locally to test

```bash
cd portfolio-fetcher
pip install -r requirements.txt
playwright install chromium   # only needed for tier2 scrapers
export GOOGLE_OAUTH_TOKEN_FILE=token.json   # or GOOGLE_SERVICE_ACCOUNT_FILE=service_account.json

python main.py --month 2026-08 --dry-run        # scrape + validate only, no Drive/Sheets writes
python main.py --month 2026-08 --amc PPFAS,MIRAE
python main.py --month 2026-08 --force          # re-fetch even if already logged this month
```

Omit `--month` to default to the previous calendar month (what the
scheduled run does).

## AMC coverage

Driven by the `AMC_Directory` sheet — each row's **Short Code** must
match a key in `scrapers/tier1_direct.py::TIER1_SCRAPERS` or
`scrapers/tier2_playwright.py::TIER2_SCRAPERS` to have a working
scraper. Currently real/confirmed:

- **PPFAS** (tier 1) — known limitation: guesses the file's "as on" date
  from the calendar rather than discovering it, so it can miss some
  months (see its own docstring).
- **MIRAE** (tier 2) — known limitation: the data API it calls returns
  only its 10 most-recent items with no confirmed pagination parameter,
  so it can miss a scheme's file in an unusually large publish batch.

Every other row (DSP, Bandhan, Quant, WhiteOak, HDFC, SBI, ICICI
Prudential, Kotak, Nippon) is registered with an explicit
`NotImplementedError` stub, not a guess — each needs the AMC's real
disclosure page individually investigated (the same way PPFAS's and
Mirae Asset's adapters were built) before it can return real data. A
stubbed AMC is logged in `Monthly_Tracker` as `Skipped` with a note
explaining why, never silently dropped.

## Monthly_Tracker columns

`Month-Year | AMC Name | Scheme/File Scope | File Name | Drive URL | Download Date | Supabase Sync Status | Notes`

`Supabase Sync Status` is one of `Pending` (uploaded, not yet read by
the backend ingestion job), `Not Found` (scraper ran, found nothing this
month), `Failed` (scraper or upload raised), or `Skipped` (no scraper
registered / scraper explicitly unimplemented for this AMC).
