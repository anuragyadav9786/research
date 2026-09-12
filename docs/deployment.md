# ThinkFin Deployment & Automation

## CI: `.github/workflows/ci.yml`

Runs on every push and pull request. Fully self-contained — **no
repository secrets required** — because the Postgres it uses is a
throwaway service container scoped to that one job run, not a real
database:

- **backend job**: spins up `postgres:16`, installs `backend/
  requirements.txt`, runs `alembic upgrade head`, runs the Phase 2 sample
  seed (`database/seeds/seed_sample_data.py` — entirely fictional data,
  see that file's header), then runs the full `pytest` suite (159 tests
  as of Phase 12).
- **frontend job**: `npm ci`, `npm run build`, `npm run lint`.

This exact sequence was manually verified against a genuinely fresh
Postgres database (not the long-lived dev database used throughout this
project's build) before being committed, specifically so "should pass in
CI" wasn't just an assumption.

## Daily NAV ingestion: `.github/workflows/daily-nav-ingestion.yml`

**Live and scheduled**, running daily at ~06:00 IST (`30 0 * * *` UTC
cron). Unlike CI, this job needs a real, persistent, CI-reachable
Postgres instance — ingested NAV data has to still be there tomorrow, so
a per-run throwaway container doesn't work here. It's backed by a
Supabase free-tier project, with `DATABASE_URL` set as a repository
secret (Settings → Secrets and variables → Actions).

**Important Supabase-specific gotcha**: use the **Session pooler**
connection string (Project Settings → Database → Connection string →
"Session pooler"), not the "Direct connection" one. The direct-connection
hostname (`db.<project-ref>.supabase.co`) resolves to an IPv6-only
address that GitHub-hosted runners cannot route to ("Network is
unreachable"); the pooler hostname (`aws-0-<region>.pooler.supabase.com`)
resolves over IPv4. The pooler also requires the username to include the
project ref (`postgres.<project-ref>`, not bare `postgres`) — Supabase's
copy-pasteable connection string already has this right, so prefer
copying it whole over hand-editing the direct-connection one.

A manual `workflow_dispatch` run was used to verify this end-to-end
before enabling the schedule: `alembic upgrade head` applied cleanly
against the live Supabase database, and `daily_pipeline` fetched real
AMFI NAV data (downloaded=14361). **That run's `records_accepted` was 0**
— expected, not a bug: this database currently only holds the fictional
Phase 2 sample funds (see `database/seeds/seed_sample_data.py`), whose
scheme codes don't match any real AMFI scheme, so every real record is
correctly rejected as unmatched by `map_to_scheme_variants`. Nothing here
will show real ingested data until real fund schemes are loaded.

This also resolved a previously open question: this project's own
sandboxed dev environment could not reach `amfiindia.com` at all
(outbound blocked — see `docs/data-sources.md`), but a GitHub-hosted
runner has ordinary internet access and reached it successfully.

If the `DATABASE_URL` secret is ever removed, the workflow fails
immediately with a clear `::error::` message naming exactly what's
missing — never a cryptic connection failure buried in a Python
traceback, and never silently "succeeding" without having ingested
anything.

## No monthly holdings/factsheet workflow yet

The product spec (Section 13) also calls for a monthly job refreshing
holdings, factsheets, AUM, expense ratios and portfolio changes. This
has deliberately **not** been built: there is no real holdings-ingestion
source yet — AMC factsheets are the intended source (see
`docs/data-sources.md`'s "Planned sources" table) and that parser doesn't
exist. A monthly workflow with nothing real to call would be automation
theater — a scheduled job that runs and does nothing meaningful — which
this project's rules treat the same as any other fabricated feature.
Build the factsheet-ingestion pipeline first (mirroring
`data_pipeline/sources/amfi/`'s structure for a new `sources/amc_factsheets/`
adapter), then this workflow.

## Backend hosting (not yet chosen)

The FastAPI backend needs a host reachable from the deployed frontend.
**Render** (free tier) is the chosen host — `render.yaml` at the repo
root is a Blueprint Render reads automatically. To deploy:

1. Render dashboard -> New -> Blueprint -> connect this GitHub repo.
   Render detects `render.yaml` and provisions a `thinkfin-backend` web
   service (root dir `backend`, `pip install -r requirements.txt`,
   `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port
   $PORT`, health check at `/api/health`).
2. When prompted for env vars, set:
   - `DATABASE_URL` — the same Supabase Session Pooler connection string
     used by `daily-nav-ingestion.yml` (see above): backend and the
     ingestion job share one database.
   - `CORS_ORIGINS` — a JSON array containing the deployed frontend's
     origin, e.g. `["https://<your-app>.vercel.app"]`. Without this the
     browser blocks the frontend's requests (CORS), even though the API
     itself is reachable.
   - `ANTHROPIC_API_KEY` — optional; leave blank to keep the AI
     Explanation Layer in its documented `available: false` state.
3. Once live, copy the service's public URL (`https://thinkfin-backend
   -<hash>.onrender.com`) into the frontend's `NEXT_PUBLIC_API_URL` (see
   below).

Render's free tier spins down after inactivity, so the first request
after a period of idleness will be slow (cold start) — acceptable for
this project's zero-budget constraint, documented here rather than
silently surprising.

## Frontend hosting

Vercel, per the original architecture (`docs/BUILD_PLAN.md`). Deployed —
set the `NEXT_PUBLIC_API_URL` environment variable in the Vercel
project's settings to the Render backend's public URL from above, then
redeploy: Next.js inlines `NEXT_PUBLIC_*` variables at build time, so
changing the env var alone does not take effect without a rebuild.

## Known dependency vulnerability (tracked, not yet fixed)

`npm audit` (frontend) currently reports 2 vulnerabilities (1 high, 1
moderate) in `postcss`, pulled in transitively by the pinned `next`
version — CSS-stringification and source-map path-traversal issues in
PostCSS itself, relevant mainly to build-time CSS processing rather than
runtime user input. The fix (`npm audit fix --force`) upgrades to
`next@16.3.5`, a breaking major-version change that needs its own
dedicated review and re-verification of the whole frontend — out of
scope for this automation pass, so it's recorded here rather than forced
through unreviewed or silently ignored.
