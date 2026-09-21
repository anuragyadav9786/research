# ThinkFin — BUILD_PLAN.md
## Phase 0: Architecture & Planning

Status: **Green-field build.** No existing repository, codebase, or infrastructure was found — this document serves as the Phase 0 deliverable (repo inspection is replaced with a from-scratch architecture proposal, per the master prompt's own instructions for this case).

---

## 1. Current State

- No frontend, backend, database, or data pipeline exists yet.
- No prior technical debt to account for.
- Nothing to preserve; nothing to migrate.
- This means Phase 1 (Project Foundation) can start clean, with no legacy constraints.

---

## 2. Confirmed Technology Stack

| Layer | Choice | Notes |
|---|---|---|
| Frontend | Next.js + TypeScript + Tailwind | Deployed on Vercel |
| Charts | Recharts | Lightweight, sufficient for rolling returns / drawdown charts |
| Backend | Python + FastAPI + Pydantic + SQLAlchemy + Alembic | All business logic and financial math live here, not in the frontend or in AI calls |
| Database | PostgreSQL (Supabase free tier initially) | Kept vendor-neutral — no Supabase-specific features in core schema |
| Data processing | Pandas, NumPy, SciPy, statsmodels | scikit-learn only if a genuine use (e.g. style/factor clustering) emerges later |
| Dev/CI | GitHub, GitHub Actions, `.env` config | No paid infra |
| Raw file storage | Local disk in dev; Google Drive for larger source documents | Postgres holds normalized data only, not raw PDFs/CSVs |

No Kubernetes, Kafka, Redis, or paid market-data APIs at this stage — consistent with Rule 5 (zero-budget, modular monolith).

---

## 3. Proposed Final Architecture

```
Next.js (Vercel)
      │  REST calls
      ▼
FastAPI backend  ──────────────►  PostgreSQL (Supabase)
   │        │                         ▲
   │        │                         │
   │        ▼                         │
   │   Analytics Engine (Pandas) ─────┘
   │   (returns, risk, overlap, stress-test —
   │    all deterministic Python, no LLM math)
   │
   ▼
AI Explanation Layer
   (reads ONLY precomputed structured JSON,
    never touches raw NAV/holdings data,
    never calculates a number)

Data Pipeline (separate scheduled process, triggered by GitHub Actions)
   sources/  → ingestion/ → validation/ → normalization/ → storage/
   (AMFI / AMC / SEBI / NSE / RBI adapters, each isolated so no
    single source is load-bearing for the whole app)
```

**Design principles carried into every phase:**
1. **Deterministic core, generative edge** — Pandas computes; AI only explains already-computed JSON. This is enforced by literally not giving the AI layer database or raw-data access — it only ever sees a metrics dict.
2. **Adapter-per-source** — each data source (AMFI, AMC, SEBI...) is an isolated module under `data_pipeline/sources/`, so a broken or discontinued source doesn't take down ingestion for everything else.
3. **Precompute, don't recompute** — analytics run as a batch job and are cached in `fund_metrics` / `analytics_runs`; the API serves precomputed rows, not live recalculation on every page load.
4. **Everything versioned and sourced** — every metric row carries `analytics_version`; every ingested record carries source + retrieval timestamp, so "where did this number come from?" is always answerable.
5. **Monolith now, splittable later** — `analytics/`, `data_pipeline/`, and `backend/app/` are separate top-level packages with clean interfaces, so any one of them could become its own service later without a rewrite.

---

## 4. Database Schema (ERD, textual)

Core fund/reference data:

```
amcs (id, name, ...)
  └─< fund_families (id, amc_id, name)
        └─< schemes (id, fund_family_id, category, benchmark_id, ...)
              └─< scheme_variants (id, scheme_id, plan[direct/regular], option[growth/idcw], amfi_code, isin)

benchmarks (id, name, index_code)
securities (id, isin, name, sector_id, ...)
sectors (id, name, parent_sector_id)

nav_history (id, scheme_variant_id, date, nav, source_id)  — indexed on (scheme_variant_id, date)
benchmark_history (id, benchmark_id, date, value, source_id)

portfolio_snapshots (id, scheme_id, as_of_date, source_id)
  └─< portfolio_holdings (id, snapshot_id, security_id, weight_pct, market_value)

fund_managers (id, name)
fund_manager_history (id, scheme_id, manager_id, start_date, end_date)

fund_metrics (id, scheme_variant_id, metric_name, value, calc_date, analytics_version)
market_regimes (id, name, start_date, end_date, regime_type)

data_sources (id, name, url, type)
data_ingestion_runs (id, source_id, started_at, completed_at, records_downloaded, records_accepted, records_rejected, status)
analytics_runs (id, analytics_version, started_at, completed_at, status)
```

User/investor data (kept in a separate schema-logical group so it can be split out first if the product ever needs multi-tenant isolation):

```
investor_profiles (id, risk_tolerance, horizon, goal, ...)
investor_portfolios (id, investor_profile_id, name)
  └─< investor_portfolio_holdings (id, portfolio_id, scheme_variant_id, units or amount)
portfolio_analysis (id, portfolio_id, analysis_json, calc_date, analytics_version)
```

Key constraints to enforce from day one:
- `scheme_variants.amfi_code` unique where not null; `securities.isin` unique.
- `nav_history` unique on `(scheme_variant_id, date)`.
- `portfolio_holdings.weight_pct` check between 0 and 100; a per-snapshot trigger/query flags total weight far from 100%.
- All `*_history` and `*_runs` tables get `created_at` and, where mutable, `updated_at`.

This directly supports the identifier hierarchy the spec calls for: **Fund Family → Scheme → Variant → Direct/Regular → Growth/IDCW**, without duplicating portfolio data across NAV variants (portfolio_snapshots hang off `scheme_id`, not `scheme_variant_id`, since the underlying holdings are identical across variants).

---

## 5. API Plan (Phase 5 preview, scaffolded now for schema alignment)

```
GET  /api/funds                        list/search funds
GET  /api/funds/{id}                   fund detail (metadata)
GET  /api/funds/{id}/returns           absolute + CAGR
GET  /api/funds/{id}/rolling-returns   1/3/5-yr rolling distributions
GET  /api/funds/{id}/risk              volatility, Sharpe, Sortino, capture ratios
GET  /api/funds/{id}/drawdown          max drawdown + recovery
GET  /api/funds/{id}/portfolio         holdings, sector/cap breakdown
GET  /api/funds/{id}/manager           manager history + attribution
GET  /api/funds/{id}/intelligence      the full precomputed decision-intelligence bundle

POST /api/funds/compare                2+ funds, structured multi-metric comparison
POST /api/portfolio/analyse            combined holdings/overlap/stress for a user portfolio

GET  /api/benchmarks
GET  /api/market/regime
GET  /api/system/data-status           ingestion freshness (Section 34 dashboard)
```

All responses go through Pydantic schemas — no SQLAlchemy models are ever returned directly.

---

## 6. Development Roadmap

Phases as defined in the master prompt, each gated on the previous phase's tests passing and errors being resolved before moving on:

| Phase | Deliverable | Gate to pass |
|---|---|---|
| 1 | Frontend + backend + Postgres scaffolding, health check, first migration | Health endpoint returns OK, migration runs clean |
| 2 | Full core schema + seed data (clearly labelled sample funds) | All core entities representable end-to-end |
| 3 | NAV ingestion (real source, e.g. AMFI's NAVAll.txt / mfapi.in) | Ingestion log shows accepted/rejected counts, no silent bad inserts |
| 4 | Analytics engine: returns, CAGR, rolling returns, volatility, Sharpe, Sortino, drawdown, recovery, alpha/beta, capture ratios | Every function unit-tested against known reference values |
| 5 | Fund Intelligence API | Structured JSON, validated schemas, no raw DB leakage |
| 6 | Fund Intelligence UI | Renders real ingested data, not placeholders |
| 7 | Holdings/Portfolio DNA engine | Concentration, sector, market-cap classification working |
| 8 | Overlap engine | Security/weighted/sector overlap + redundancy detection |
| 9 | Multi-fund portfolio analysis | Combined exposure, correlation, stress inputs |
| 10 | Market-cycle engine | Regime table + fund behaviour per regime (manual regime table acceptable initially) |
| 11 | Stress-test engine | Configurable scenarios, clearly labelled as hypothetical |
| 12 | AI explanation layer | Reads only structured JSON; no invented figures |
| 13 | Automation (GitHub Actions daily/monthly pipelines) | Every run logged with status |

---

## 7. Open Decisions Before Phase 1 Starts

These need a call before scaffolding, since they shape the schema/migrations:

1. **NAV source for Phase 3** — AMFI's daily NAVAll.txt bulk file vs. `mfapi.in` (wraps AMFI, easier per-scheme queries but third-party). Recommend starting with `mfapi.in` for developer speed, with an adapter boundary so swapping to raw AMFI later is a source-module change, not a rewrite.
2. **Holdings/portfolio data source** — AMC factsheets (PDF, monthly, inconsistent formats) are the realistic free option; this will need a per-AMC parser or manual entry initially. Worth deciding scope (how many AMCs/schemes for MVP) before Phase 2 seed data.
3. **Benchmark data source** — NSE index data availability/licensing for free use should be confirmed before Phase 3. **Update (Phase 17):** the benchmark data engine (schema, lazy fetch/cache, provider abstraction) is built and wired end-to-end, with an `NSEProvider` implementation, now enabled (`Settings.benchmark_nse_provider_enabled = true`). Still outstanding: its request/response shape has never been confirmed against a live response (every development environment so far has had no outbound network access — an explicit 403 policy denial on niftyindices.com, not a transient failure), and its terms of use for this kind of automated fetch haven't been separately confirmed. Enabling it anyway was a deliberate choice — a shape mismatch fails closed to "Data unavailable," never a wrong number — but this open decision isn't fully resolved. See `docs/data-sources.md` section 4.
4. **Risk-free rate source and update cadence** for Sharpe — e.g. RBI 91-day T-bill rate, manually configured vs. ingested.

None of these block starting Phase 1 (foundation has no data dependency), but 1–3 need an answer before Phase 3.

---

**Next step:** on approval of this plan, Phase 1 begins — repo scaffolding, frontend/backend/DB wiring, health check, first Alembic migration.
