# ThinkFin API — Phase 5: Fund Research

Base path: `/api`. All responses are validated Pydantic schemas
(`backend/app/schemas/funds.py`) — SQLAlchemy models never cross this
boundary (Section 20).

## Fund identity model

An endpoint's `{fund_id}` is a **Scheme** id (e.g. "Northbridge Bluechip
Equity Fund"), not a specific NAV series — a scheme has multiple
`scheme_variants` (direct/regular x growth/idcw) that share one portfolio
but have different NAV histories. Every analytics endpoint below accepts
`plan` (`direct` | `regular`, default `direct`) and `option` (`growth` |
`idcw`, default `growth`) query parameters to select which variant's NAV
series to compute against. Requesting a plan/option combination the fund
doesn't have returns `404`, not a fabricated/substituted result.

## Endpoints

| Method & path | Purpose |
|---|---|
| `GET /api/funds` | List/search funds. Query: `search` (name substring), `category` (exact), `amc` (name substring). |
| `GET /api/funds/{fund_id}` | Fund detail: metadata + all variants with their latest NAV. |
| `GET /api/funds/{fund_id}/returns` | Absolute CAGR for 1y/3y/5y/7y/10y windows, each explicitly marked `available`/`reason` if the NAV history doesn't reach that far back. |
| `GET /api/funds/{fund_id}/risk` | Volatility, downside deviation, Sharpe, Sortino, upside/downside capture, beta, Jensen's alpha. |
| `GET /api/funds/{fund_id}/rolling-returns` | Rolling-CAGR distribution + benchmark-consistency stats for a given `window_years` (default 3, query param). |
| `GET /api/funds/{fund_id}/drawdown` | Maximum drawdown episode: peak/trough dates and NAVs, recovery date or explicit "not yet recovered". |
| `GET /api/funds/{fund_id}/nav-history` | Raw NAV/benchmark series (Phase 6 addition — no analytics, just the data feed the frontend's charts render). |
| `GET /api/funds/{fund_id}/portfolio` | Portfolio DNA + concentration (Phase 7): top holdings, sector/market-cap allocation, HHI. **Scheme-level, not variant-specific** — holdings are identical across a scheme's plan/option variants, so this endpoint takes no `plan`/`option` params. |
| `GET /api/funds/{fund_id}/overlap?compare_to={other_id}` | Pairwise fund overlap (Phase 8): common holdings, weighted/sector overlap, HHI-style overlap label, return correlation. Also scheme-level. Rejects comparing a fund to itself (`400`). |
| `GET /api/funds/{fund_id}/intelligence` | Bundles the variant-specific analytics (except `nav-history`, `portfolio` and `overlap`) plus fund/variant metadata into one response. |
| `POST /api/portfolio/analyse` | Multi-fund Portfolio Analysis (Phase 9): combine 2-10 funds by weight into look-through holdings, sector/market-cap allocation, concentration, pairwise overlap, and portfolio-level risk/drawdown. **Stateless** — see below. |
| `GET /api/funds/{fund_id}/market-regimes` | Market-Cycle Behaviour (Phase 10): fund vs. benchmark return, volatility and max drawdown within each defined market regime, plus a deterministic outperform/underperform summary per regime. |
| `GET /api/market/regimes` | Plain reference list of all defined market regimes (name, type, date range) — no fund attached. |

Interactive docs: `http://localhost:8000/docs` (Swagger UI, auto-generated
from the same Pydantic schemas).

### `POST /api/portfolio/analyse`

Request body: `{"holdings": [{"fund_id": 13, "weight_pct": 60}, {"fund_id": 14, "weight_pct": 40}]}`
— 2 to 10 holdings, `weight_pct` values must sum to ~100% (±0.5 tolerance,
`400` otherwise), no duplicate `fund_id`s (`400`), every `fund_id` must
resolve to an existing scheme (`404` otherwise).

**Stateless by design**: this computes a hypothetical combination on
demand from the request body — it does not read or write
`investor_portfolios`. There is no authentication system yet (Section 25
lists it as a future expansion, not built), and persisting a "my
portfolio" record with no account to own it would be a half-built data
model; the schema is ready for that once auth exists.

Everything the response reports is built by combining existing per-fund
analytics (Phase 7's concentration/allocation, Phase 8's overlap, Phase
4's risk/drawdown) via `analytics/portfolio.py`'s weight-combination
formulas — no new ad hoc "portfolio risk" calculation exists.

## Design decisions worth knowing

- **Insufficient data is never silently hidden or faked.** Every metric
  that can't be computed from the available NAV history returns
  `"available": false"` and a `reason` (e.g. `"insufficient_history"`),
  rather than omitting the field or returning a misleading zero.
- **Computed live, not precomputed.** These endpoints call the Phase 4
  analytics engine directly on each request rather than reading from the
  `fund_metrics` precomputed-cache table (Section 31's "precompute, don't
  recompute" guidance). This is fine at current data volumes; wiring up
  `fund_metrics`/`analytics_runs` is a follow-up once real ingestion (Phase
  3, pending live network access) brings in the full fund universe and
  request volume grows.
- **No qualitative "Strong/Moderate/Weak" scoring yet.** `/intelligence`
  returns only directly computable numbers. The qualitative assessment
  framework from the product spec's Section 15 needs the Portfolio DNA,
  Concentration, and Manager Skill engines (later phases) to ground it in
  real data — producing a plausible-sounding label without those inputs
  would be a fabricated conclusion (Rule 2/4), so it's deferred, not faked.
- **Every response carries the compliance disclaimer** (Section 33):
  historical performance is not a guarantee of future results.
- **`/portfolio` only reports what's disclosed.** Weights are of disclosed
  holdings only; `total_disclosed_weight_pct` is always shown alongside
  concentration figures so a portfolio with only top-10 holdings on file
  doesn't imply undisclosed exposure (cash, remaining holdings) is zero.
  Securities with no market-cap classification (all bonds, currently) are
  grouped as `"unclassified"`, never guessed into a cap bucket.
- **`/overlap` is scheme-level and symmetric.** No `plan`/`option` params
  (holdings don't vary by variant); `weighted_overlap_pct` and
  `common_securities_count` are the same whichever fund is `{fund_id}`
  and whichever is `compare_to` — verified in
  `test_overlap_is_symmetric_in_weighted_pct`.
- **`/market-regimes` never hides where its regime data comes from.**
  Every response carries a `methodology_note` stating plainly that the
  current sample dataset's regimes are illustrative windows over
  synthetic data, not verified real-world market classifications — see
  `docs/data-sources.md`. Regime summaries are deterministic string
  templates built from the computed return numbers, never an LLM call.

## Testing

`backend/tests/api/test_funds.py`, `test_portfolio.py`, `test_overlap.py`,
`test_portfolio_analysis.py` and `test_market_regime.py` run all of the
above against the real Phase 2 seed data (no mocking) via FastAPI's
`TestClient`: fund listing/search, full-detail variant listings, each
analytics endpoint's happy path, the explicit insufficient-history path
(10-year window against ~4 years of seed history), top-holdings/HHI/
allocation correctness (including the bonds' "unclassified" case),
pairwise overlap correctness and symmetry, multi-fund combination
correctness (hand-verified effective weights for a 3-fund mix, allocation
reconciliation), per-regime behaviour correctness (excess return
reconciliation, summary text matching the sign of over/underperformance),
and 404/422/400 error handling.
