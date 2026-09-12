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

**Not yet scheduled.** Its `schedule:` trigger is commented out in the
workflow file itself. Unlike CI, this job needs a real, persistent,
CI-reachable Postgres instance — ingested NAV data has to still be there
tomorrow, so a per-run throwaway container doesn't work here.

To enable it:

1. Provision a Postgres instance reachable from GitHub-hosted runners
   (Supabase's free tier is the natural zero-budget choice — see
   `docs/data-sources.md` and `docs/BUILD_PLAN.md`'s open decisions).
2. Add its connection string as a repository secret named `DATABASE_URL`
   (Settings → Secrets and variables → Actions).
3. Run the workflow once by hand (Actions tab → "Daily NAV Ingestion" →
   Run workflow) to confirm it can actually reach both that database and
   AMFI, before trusting a schedule to it.
4. Uncomment the `schedule:` block in the workflow file.

If the secret is missing, the workflow fails immediately with a clear
`::error::` message naming exactly what's missing — never a cryptic
connection failure buried in a Python traceback, and never silently
"succeeding" without having ingested anything.

**A second, independent unknown**: this project's own sandboxed dev
environment could not reach `amfiindia.com` at all (outbound blocked —
see `docs/data-sources.md`), so the live AMFI fetch has never been
exercised end-to-end from here. A GitHub-hosted runner has ordinary
internet access and may well succeed where this sandbox couldn't, but
that hasn't been confirmed. Step 3 above is exactly how to find out.

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

The FastAPI backend needs a host reachable from the deployed frontend —
Render, Railway, or Fly.io free tiers are the natural zero-budget
candidates (see the main README). Not provisioned or evaluated yet.

## Frontend hosting

Vercel, per the original architecture (`docs/BUILD_PLAN.md`) — connect
the repo, set `NEXT_PUBLIC_API_URL` to wherever the backend ends up
hosted. Not yet deployed.

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
