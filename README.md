# ThinkFin — Mutual Fund Decision Intelligence Platform

A research platform that explains **why** a mutual fund should or should not be
considered for a portfolio — performance quality, risk survival, portfolio DNA,
overlap, manager skill, and stress behaviour — rather than just ranking funds by
returns.

This is a zero-budget, modular-monolith build. See `docs/BUILD_PLAN.md` for the
full Phase 0 architecture, database ERD, API plan, and development roadmap.

## Stack

- **Frontend**: Next.js (TypeScript, Tailwind, Recharts) → deploy on Vercel
- **Backend**: FastAPI + SQLAlchemy + Alembic (Python)
- **Database**: PostgreSQL (Supabase free tier in production; local Postgres/Docker in dev)
- **Analytics**: Pandas/NumPy/SciPy — all financial math is deterministic Python, never LLM-calculated
- **AI layer**: reads only precomputed structured JSON to generate explanations; never touches raw data or computes numbers

## Project layout

```
frontend/           Next.js app
backend/             FastAPI app (app/api, app/models, app/schemas, app/services, app/repositories, app/core)
analytics/           Deterministic financial calculation modules (Phase 4+)
data_pipeline/        Source adapters + ingestion/validation/normalization (Phase 3+)
database/            Alembic migrations + seed data (top-level, shared by backend)
docs/                BUILD_PLAN.md and (later) architecture/methodology docs
.github/workflows/   CI
```

## Local development

### 1. Database

Either run Postgres via Docker:

```bash
docker compose up -d
```

or use a local Postgres install with a `thinkfin` database matching
`backend/.env`'s `DATABASE_URL`.

### 2. Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate      # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env           # adjust DATABASE_URL if needed
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Health check: `curl http://localhost:8000/api/health` → `{"status":"ok","database":"ok"}`

Run tests: `pytest -q`

### 3. Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

Visit `http://localhost:3000` — the dashboard shell renders the backend's live
health-check response, confirming the full stack is wired end-to-end.

## Deployment (later phases)

- **Frontend** → Vercel (connect the repo, set `NEXT_PUBLIC_API_URL` to the deployed backend URL)
- **Database** → Supabase (swap `DATABASE_URL` in the backend's environment; schema is standard PostgreSQL with no Supabase-specific features)
- **Backend** → any Python host reachable from Vercel (Render, Railway, Fly.io free tiers, etc. — to be decided)

## Rules this codebase follows (from the project brief)

- No fabricated financial data — mock data is always clearly labelled and never mixed with production data.
- No LLM does financial arithmetic — CAGR, Sharpe, Sortino, drawdown, alpha/beta, overlap, concentration, etc. are explicit, tested Python functions (see `analytics/`, from Phase 4 onward).
- Every ingested figure carries source, source URL, retrieval timestamp, and data period (`data_sources`, `data_ingestion_runs`).
- Every computed metric carries an `analytics_version` so methodology changes are traceable over time.
- Historical performance is never presented as a guarantee; stress tests are explicitly hypothetical.

### 4. Sample data (Phase 2)

The core schema ships empty. To exercise it end to end with a small set of
**entirely fictional, clearly-labelled** sample funds (see the file header
in `database/seeds/seed_sample_data.py` for exactly what is and isn't real):

```bash
cd backend && source .venv/bin/activate
python ../database/seeds/seed_sample_data.py            # idempotent
python ../database/seeds/seed_sample_data.py --reset     # wipe + reseed
```

This creates 2 sample AMCs, 4 schemes, 8 scheme variants (direct/regular ×
growth), synthetic NAV and benchmark history (seeded random walk, not real
market data), sample portfolio holdings, managers, and market regimes.

### 5. Analytics engine (Phase 4)

Deterministic financial calculations live in `analytics/` at the repo root
(never in the frontend, never computed by an LLM — see Rule 4). Covered so
far: CAGR/simple returns, rolling returns + benchmark consistency,
annualized volatility, Sharpe, Sortino, max drawdown + recovery, upside/
downside capture, beta and Jensen's alpha. Full methodology — formulas,
assumptions, limitations — is in `docs/analytics-methodology.md`.

```bash
cd backend && source .venv/bin/activate
pytest tests/analytics -q
```

### 6. NAV ingestion pipeline (Phase 3)

`data_pipeline/` implements the AMFI NAVAll.txt adapter end to end: fetch
(`sources/amfi/client.py`) -> parse (`sources/amfi/parser.py`) -> validate
(`validation/nav_validation.py`) -> map to existing schemes
(`normalization/scheme_mapping.py`) -> upsert + log
(`storage/database_writer.py`, `ingestion/nav_ingestion.py`). Every run is
logged to `data_ingestion_runs` with accept/reject counts, success or
failure. Full source documentation, including exactly what has and hasn't
been verified live, is in `docs/data-sources.md`.

```bash
cd backend && source .venv/bin/activate
pytest tests/unit/test_amfi_parser.py tests/unit/test_nav_validation.py \
       tests/unit/test_amfi_client.py tests/integration/test_nav_ingestion.py -q

# Run for real once network access + Phase 2 seed data are available:
python -m data_pipeline.orchestration.daily_pipeline
```

### 7. Fund Intelligence API (Phase 5)

`GET /api/funds`, `/api/funds/{id}`, `/api/funds/{id}/{returns,risk,
rolling-returns,drawdown,intelligence}` — structured, validated JSON built
on the Phase 4 analytics engine. Full documentation, including the fund/
variant identity model and design decisions, is in `docs/api.md`. Try it
live at `http://localhost:8000/docs` once the backend is running.

```bash
cd backend && source .venv/bin/activate
pytest tests/api/test_funds.py -q
```

### 8. Fund Intelligence UI (Phase 6)

The Next.js frontend now has a real Research section, not just the health
check shell: `/research` (search/browse funds) and `/research/[fundId]`
(the fund intelligence page — returns, risk, a NAV-vs-benchmark chart,
rolling-return distribution with benchmark consistency, and drawdown, with
direct/regular and growth/IDCW plan toggles). Built against a small
Phase-6 addition to the API, `GET /api/funds/{id}/nav-history`, since
charting needs the raw series, not just computed metrics.

```bash
# with the backend running on :8000
cd frontend && npm run dev
# visit http://localhost:3000/research
```

Verified in a real browser (Playwright + the pre-installed Chromium) against
live seeded data, including the search/filter form, plan/option toggles,
the rolling-returns window selector, the insufficient-history and
no-such-variant states, and a themed 404 page. See `docs/api.md` for the
new endpoint.

### 9. Holdings Engine — Portfolio DNA & Concentration (Phase 7)

`GET /api/funds/{id}/portfolio` — top holdings, sector allocation,
market-cap allocation, and concentration (HHI + top-5/top-10 weight),
computed by `analytics/concentration.py` from the Phase 2 seed portfolio
snapshots. Scheme-level (not variant-specific: holdings don't depend on
plan/option). Required a small schema addition,
`securities.market_cap_category` (nullable — `null` for bonds and
anything unclassified, grouped as `"unclassified"` rather than guessed).
Wired into the fund detail page as a "Portfolio DNA & Concentration"
section. See `docs/analytics-methodology.md` for the HHI methodology and
`docs/api.md` for the endpoint.

```bash
cd backend && source .venv/bin/activate
pytest tests/analytics/test_concentration.py tests/api/test_portfolio.py -q
```

Cross-fund "hidden concentration" (seeing the *same* stock/sector
overexposure across several funds an investor holds) is explicitly out of
scope here — that needs the Overlap Engine, Phase 8.

### 10. Fund Overlap Engine (Phase 8)

`GET /api/funds/{id}/overlap?compare_to={other_id}` — pairwise overlap
between two funds: common holdings (weight in each), weighted overlap %
(the standard "shared exposure" methodology), sector overlap, an overlap
label (documented as a practitioner heuristic, not an official standard —
unlike HHI's DOJ/FTC thresholds), and return correlation. Implemented in
`analytics/{overlap,correlation}.py`. A new `/research/compare` page lets
you pick any two funds and see the full breakdown, linked from every fund
detail page ("Compare with…"). See `docs/analytics-methodology.md` for
the overlap methodology and `docs/api.md` for the endpoint.

```bash
cd backend && source .venv/bin/activate
pytest tests/analytics/test_overlap.py tests/analytics/test_correlation.py tests/api/test_overlap.py -q
```

Multi-fund (3+) "hidden concentration" and combined-portfolio analysis —
the rest of Section 9/11 — need Phase 9's Portfolio Analysis engine.

### 11. Portfolio Analysis (Phase 9)

`POST /api/portfolio/analyse` — combine 2-10 funds by weight into a single
hypothetical portfolio: look-through combined holdings, sector/market-cap
allocation, concentration (HHI on the combined exposure), pairwise
overlap between every constituent pair, and portfolio-level volatility/
Sharpe/Sortino/drawdown computed from the weight-combined return series.
Built entirely from existing Phase 4/7/8 analytics via
`analytics/portfolio.py`'s combination formulas — no new risk/
concentration math. **Stateless**: no auth system exists yet, so this
takes funds+weights in the request rather than reading/writing a
persisted "my portfolio" (see `docs/api.md` for why).

A new `/portfolio` page lets you build a hypothetical portfolio from 2-10
funds with a weight per fund and see the full breakdown — linked from the
main nav on every page.

```bash
cd backend && source .venv/bin/activate
pytest tests/analytics/test_portfolio.py tests/api/test_portfolio_analysis.py -q
```

### 12. Market-Cycle Engine (Phase 10)

`GET /api/funds/{id}/market-regimes` — fund vs. benchmark return,
volatility and max drawdown within each defined market regime, plus a
deterministic (templated, not LLM-written) outperform/underperform
summary per regime and an overall "beat benchmark in N of M periods"
rollup. `GET /api/market/regimes` lists the regimes themselves. Built on
`analytics/market_regime.py`, which reuses the existing returns/risk/
drawdown functions restricted to each regime's date window — simple
(non-annualized) return rather than CAGR, since regimes are often
sub-annual.

**Data provenance, stated plainly**: the sample dataset's regimes are
illustrative windows shaped to match the *synthetic* seed's own
trajectory, not verified real market classifications — every response
carries this as `methodology_note`, and it's documented in
`docs/data-sources.md`.

Wired into the fund detail page as a "Market-Cycle Behaviour" section,
and into a new `/market` page (finally a real destination for the
previously-placeholder "Market Intelligence" nav item — sector trends and
a broader risk-environment view remain unbuilt).

```bash
cd backend && source .venv/bin/activate
pytest tests/analytics/test_market_regime.py tests/api/test_market_regime.py -q
```

## Status

**Phase 0, 1, 2, 4, 5, 6, 7, 8, 9 and 10** complete. **Phase 3** (NAV
ingestion) is architecturally complete and tested down to the network
boundary — see Known limitations for exactly what remains to verify.

Next: **Phase 11** — Stress-Test Engine (configurable hypothetical
scenarios — e.g. "Nifty falls 25%", "midcaps fall 40%" — estimating
fund/portfolio impact from historical relationships and exposure,
explicitly labelled as hypothetical, never predictive).

### Known limitations

- The analytics engine has been smoke-tested against the Phase 2 synthetic
  seed data (runs cleanly, produces sane output), but that seed generates
  the fund and its benchmark as *independent* random walks — so beta/alpha
  figures computed against it are not representative of a real fund. This
  is a property of the sample data, not the analytics functions (which are
  unit-tested against known values).
- **Phase 3's live network fetch has not been executed** in this dev
  environment — outbound HTTPS to `amfiindia.com` (and `api.mfapi.in`) is
  blocked by this sandbox's network policy (confirmed via a 403 policy
  denial on the proxy's CONNECT attempt). Everything downstream of the
  fetch — parsing, validation, scheme mapping, storage, idempotency,
  failure logging — is tested end-to-end against the real database using
  a synthetic fixture in place of the live download (see
  `backend/tests/integration/test_nav_ingestion.py`). Running
  `python -m data_pipeline.orchestration.daily_pipeline` from an
  environment with outbound internet access, and confirming it inserts
  real NAV rows, is the one remaining step before Phase 3 can be marked
  fully done.
- The pipeline only ingests NAV for `scheme_variants` that already exist
  in the database (matched by AMFI code or ISIN) — it deliberately never
  creates a new scheme from a NAV file alone (see
  `data_pipeline/normalization/scheme_mapping.py`). Onboarding new schemes
  needs curated identity data (AMC, category, plan/option), which is a
  separate, not-yet-built workflow.
- No GitHub Actions workflow exists yet to run this daily (Phase 13). That
  needs a deployed, CI-reachable Postgres instance (e.g. Supabase) as a
  `DATABASE_URL` secret, which hasn't been provisioned — adding a workflow
  that can't actually run against real infrastructure would violate the
  "run and verify before moving on" rule this build follows.
