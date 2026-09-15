# Portfolio Fetcher

A scheduled worker that fetches AMC monthly portfolio-disclosure Excel
files and stores them in Google Drive, logging every attempt (success
or failure) to a master catalog Google Sheet. This is the *collection*
half of the pipeline — a separate ingestion job (in `backend/`) reads
from Drive and turns these files into structured `PortfolioHolding`
rows; this worker never touches the database.

Currently onboarded: **PPFAS** (Parag Parikh) only. Add more AMCs by
writing a new `fetch_<amc>(month_str)` function in `main.py` and
registering it in `AMC_ADAPTERS` — see the docstring on `fetch_ppfas`
for the shape each adapter returns.

This runs as a Render Cron Job, not a Vercel deployment — `vercel.json`
here (`{"builds": []}`) is a deliberate no-op so that if Vercel's
monorepo auto-detection ever creates a project for this folder again
(it did once — a bare `main.py` with no `app`/`application`/`handler`
fails Vercel's Python function requirement, since this is a batch
script, not a web endpoint), it has nothing to build instead of
failing on every push.

**Known limitation:** PPFAS's disclosure page only reveals the current
month's real download link via client-side JavaScript, which a plain
HTTP GET (what this worker does) can't see. `fetch_ppfas` guesses the
URL from PPFAS's known filename pattern instead of actually discovering
it, so it can fail some months (a market holiday shifting the "as on"
date, or PPFAS changing the pattern) — that's logged as `NOT_FOUND` in
the catalog sheet rather than silently skipped, so it's visible for a
manual check. A proper fix means fetching the page with a headless
browser instead of a plain GET.

## 1. Create the Google Service Account

1. In the [Google Cloud Console](https://console.cloud.google.com/), create (or pick) a project, then go to **APIs & Services → Library** and enable:
   - **Google Drive API**
   - **Google Sheets API**
2. Go to **APIs & Services → Credentials → Create Credentials → Service Account**. Give it any name (e.g. `thinkfin-portfolio-fetcher`).
3. Open the new service account → **Keys → Add Key → Create new key → JSON**. This downloads a JSON file — its *entire contents* are what goes into the `GOOGLE_SERVICE_ACCOUNT_JSON` env var below. Treat it as a secret; don't commit it.
4. Copy the service account's email address (looks like `thinkfin-portfolio-fetcher@<project>.iam.gserviceaccount.com`).
5. **Share access with that email**, since a service account has no access to your Drive by default:
   - Open the Drive Master Folder (`1hSNV629OnGOchyP0coX72lVA7-Eg1kAx`) — sharing it covers the Monthly Portfolios subfolder too, since Drive permissions are inherited by nested folders/files it creates — and share it with the service account's email as **Editor**.
   - Open the Master Catalog Sheet (`1sSIAhoPCMHYQH6K5kF9oOZwAp7Llbyrr8d9Db0-YCFU`) and share it with the same email as **Editor**.

## 2. OAuth setup for Drive uploads (required)

Service accounts have **zero storage quota** on a personal (non-Workspace)
Google account. Sharing the Drive folder/Sheet with the service account as
Editor (step 5 above) is enough for it to *read* and for Sheets writes to
work, but any file it tries to *create* in Drive fails immediately with
`HttpError 403: Service Accounts do not have storage quota`, regardless of
sharing — Google makes the service account the owner of any file it
creates, and it has no quota to own anything with. Google's suggested
workarounds (Shared Drives, domain-wide delegation) are both
Workspace-only features, unavailable on a plain Gmail account.

The fix: Drive uploads run as OAuth credentials for a real Google account
(the same one that owns the Drive Master Folder) instead of the service
account, so uploaded files count against that account's own quota like
any normal upload. The service account is still used for the Sheets
catalog write, which isn't affected by this quota restriction.

1. In the same Google Cloud project, go to **APIs & Services → Credentials → Create Credentials → OAuth client ID**. Application type: **Desktop app**. Note the generated **Client ID** and **Client Secret**.
   - If prompted to configure an OAuth consent screen first, choose **External**, fill in the required app name/support email, and add your own Google account as a **test user** (test-mode apps don't need Google's review).
2. Run the one-time helper script locally (not on Render):
   ```bash
   cd portfolio-fetcher
   pip install google-auth-oauthlib
   python get_oauth_refresh_token.py
   ```
   Paste in the Client ID and Client Secret from step 1 when prompted. A browser window opens — sign in as the Google account that owns the Drive Master Folder (e.g. `anuragyadav9786@gmail.com`) and approve access. The script then prints three values.
3. Add those three values as env vars in Render (see step 3 below): `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_OAUTH_REFRESH_TOKEN`.

If these three env vars aren't set, `main.py` falls back to using the
service account for Drive too — which will hit the storage-quota error
above on a personal account, but is the correct behavior if Drive is ever
migrated to a Workspace Shared Drive, where service accounts work fine
and this whole OAuth step becomes unnecessary.

## 3. Add the credentials to Render

This runs as a Render **Cron Job** — note that Cron Jobs need a paid
Render plan; they're not available on the free tier, unlike the main
backend web service. Render's Blueprint (`render.yaml`) auto-provisions
`web`/`worker` services but not Cron Jobs, so create this one by hand:

1. Render dashboard → **New → Cron Job** → connect this GitHub repo.
2. **Root Directory**: `portfolio-fetcher`
3. **Build Command**: `pip install -r requirements.txt`
4. **Command**: `python main.py`
5. **Schedule**: `30 18 10 * *` (this is UTC — 18:30 UTC = 23:30 IST, i.e. 11:30 PM IST on the 10th of every month)
6. Under **Environment**, add:
   - `GOOGLE_SERVICE_ACCOUNT_JSON` — paste the *entire* downloaded JSON key file content as one value (Render's env var editor handles multi-line values fine).
   - `DRIVE_MONTHLY_FOLDER_ID` = `1acNwjxV2mJnEZ9BDAlKoDZpZTVav9h_5`
   - `MASTER_CATALOG_SHEET_ID` = `1sSIAhoPCMHYQH6K5kF9oOZwAp7Llbyrr8d9Db0-YCFU`
   - `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_OAUTH_REFRESH_TOKEN` — the three values printed by `get_oauth_refresh_token.py` in step 2 above. Required for Drive uploads to work on a personal Google account (see step 2).

`render.yaml` at the repo root documents this same configuration for
reference (marked `sync: false` for the JSON secret, same convention
as the backend's `DATABASE_URL`), but since Blueprints don't provision
Cron Jobs, use the dashboard steps above rather than expecting the
Blueprint to pick this up automatically.

## 4. Run it locally to test

```bash
cd portfolio-fetcher
pip install -r requirements.txt
export GOOGLE_SERVICE_ACCOUNT_JSON='<paste the full JSON key content>'
export GOOGLE_OAUTH_CLIENT_ID='<from step 2>'
export GOOGLE_OAUTH_CLIENT_SECRET='<from step 2>'
export GOOGLE_OAUTH_REFRESH_TOKEN='<from step 2>'
python main.py --month 2026-08
```

Omit `--month` to default to the previous calendar month (matching
what the scheduled run does — portfolios published in month N cover
month N-1).

## Catalog sheet columns

Each run appends one row per AMC attempted:

| month | amc | scheme_hint | status | detail | fetched_at |
|---|---|---|---|---|---|

`status` is one of `OK`, `NOT_FOUND` (adapter ran but found nothing —
e.g. PPFAS's URL guess failed), `FAILED` (the adapter itself raised),
or `UPLOAD_FAILED` (found the file but the Drive upload failed).
`detail` holds the Drive view link on success, or the error message.
