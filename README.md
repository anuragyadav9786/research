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

## Status

**Phase 0-2** complete (see above). **Phase 4** (analytics engine) is also
complete and unit-tested against independently computed reference values;
**Phase 3** (real NAV ingestion) is still open — see Known limitations.

Next: **Phase 3** — real NAV ingestion (AMFI/mfapi.in adapter), then
Phase 5 (Fund Intelligence API) to expose the analytics engine's output.

### Known limitations

- The analytics engine has been smoke-tested against the Phase 2 synthetic
  seed data (runs cleanly, produces sane output), but that seed generates
  the fund and its benchmark as *independent* random walks — so beta/alpha
  figures computed against it are not representative of a real fund. This
  is a property of the sample data, not the analytics functions (which are
  unit-tested against known values); real NAV/benchmark data will behave
  more realistically once Phase 3 lands.
- Phase 3 (real NAV ingestion) has not been executed against a live source
  in this dev environment — outbound network access to amfiindia.com and
  api.mfapi.in was blocked by this sandbox's network policy during
  development. The ingestion pipeline architecture is designed against
  these real sources but must be verified end-to-end in an environment
  with outbound internet access before being considered done.
