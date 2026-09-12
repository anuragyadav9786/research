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
| `GET /api/funds/{fund_id}/intelligence` | Bundles the variant-specific analytics (except `nav-history` and `portfolio`) plus fund/variant metadata into one response. |

Interactive docs: `http://localhost:8000/docs` (Swagger UI, auto-generated
from the same Pydantic schemas).

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

## Testing

`backend/tests/api/test_funds.py` and `test_portfolio.py` run all of the
above against the real Phase 2 seed data (no mocking) via FastAPI's
`TestClient`: fund listing/search, full-detail variant listings, each
analytics endpoint's happy path, the explicit insufficient-history path
(10-year window against ~4 years of seed history), top-holdings/HHI/
allocation correctness (including the bonds' "unclassified" case), and
404/422 error handling.
