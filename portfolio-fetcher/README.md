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

## 2. Move the Drive folder into a Shared Drive (required)

Service accounts have **zero storage quota** of their own. Sharing the
Drive folder/Sheet with the service account as Editor (step 5 above) is
enough for it to *read* and for Sheets writes to work, but any file it
tries to *create* directly in someone's personal "My Drive" fails with
`HttpError 403: Service Accounts do not have storage quota` — Google
makes the service account the owner of any file it creates, and it has
no quota to own anything with.

A **Shared Drive** (Workspace-only — this account has it) sidesteps this
entirely: storage there belongs to the Shared Drive itself, not any
individual member, so the service account can create files in it with no
quota problem. This is simpler than the personal-Gmail workaround (OAuth
as a real user account) since it needs no browser consent flow and no
extra credentials.

1. In Google Drive, click **Shared drives** in the left sidebar → **+ New** → give it a name (e.g. `ThinkFin Portfolios`).
2. Click into it → top-left dropdown/**Manage members** → add the service account's email (`thinkfin-portfolio-fetcher@<project>.iam.gserviceaccount.com`) as **Content Manager**.
3. Move the existing Drive Master Folder (`1hSNV629OnGOchyP0coX72lVA7-Eg1kAx`, which contains the Monthly Portfolios subfolder) into this Shared Drive: right-click the folder in "My Drive" → **Move to** → pick the new Shared Drive. Folder/file IDs stay the same after a move, so `DRIVE_MONTHLY_FOLDER_ID` below doesn't need to change.
   - If "Move to" isn't available (e.g. cross-account restrictions), create a fresh Master Folder + Monthly Portfolios subfolder directly inside the Shared Drive instead, and use its new folder ID for `DRIVE_MONTHLY_FOLDER_ID` below.
4. The Master Catalog Sheet does **not** need to move — appending rows to an existing file isn't affected by the storage-quota restriction, only *creating new files* is.

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
   - `DRIVE_MONTHLY_FOLDER_ID` = `1acNwjxV2mJnEZ9BDAlKoDZpZTVav9h_5` (or the new folder's ID, if you created a fresh one directly inside the Shared Drive in step 2 above)
   - `MASTER_CATALOG_SHEET_ID` = `1sSIAhoPCMHYQH6K5kF9oOZwAp7Llbyrr8d9Db0-YCFU`

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
