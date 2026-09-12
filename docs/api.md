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
| `GET /api/funds/{fund_id}/stress-test` | Stress-Test Engine (Phase 11): hypothetical scenario impact estimates. 3 of 7 spec scenarios are computed (broad market via beta, midcap/sector via disclosed exposure); the other 4 (rates, recession, INR, inflation) are explicitly marked `available: false` — no fabricated sensitivities for data this platform doesn't have. |
| `GET /api/funds/{fund_id}/ai-summary` | AI Explanation Layer (Phase 12): a human-readable summary generated from the same figures the other endpoints above already computed. The AI performs no calculation and every number it writes is verified against those figures before being returned — see below. |

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

### `GET /api/funds/{fund_id}/ai-summary`

Architecture (Section 24):

```
Existing analytics endpoints (returns, risk, drawdown, rolling,
market-regimes, portfolio) — already computed, already tested
        |
        v
build_fund_facts() — a small, flat, named dict of just the figures
above (app/services/ai_explanation_service.py)
        |
        v
One LLM call, given ONLY that dict, instructed to use only those numbers
        |
        v
validate_no_fabricated_numbers() — every number in the AI's text must be
traceable (within rounding tolerance) to a number in the facts dict, or
the response is discarded — never shown unverified
        |
        v
{"available": true, "summary": "...", "facts_used": {...}}
```

**The AI never computes a financial number.** It's given the same figures
every other endpoint above already produced and tested, and its only job
is to describe them in plain language. `facts_used` is always returned
alongside the summary (or instead of one, if generation failed) so the
claim "every number is traceable" is checkable, not just asserted.

**Response when working**: `{"available": true, "summary": "...",
"facts_used": {...}, "ai_disclaimer": "...", "disclaimer": "..."}`.

**Response when the AI service isn't configured** (no `ANTHROPIC_API_KEY`
— the expected state in this dev environment, see Known limitations
below): `{"available": false, "reason": "AI explanation layer is not
configured...", "summary": null, "facts_used": {...}}` — `facts_used` is
still populated from real computed analytics even when no summary could
be generated, so the endpoint is useful for inspecting what data the AI
*would* see.

**Response when the model's output fails the fabrication check**: same
shape, `reason` names the specific unmatched number(s). This is treated
as a bug in that one generation, not a reason to relax the check — the
unverified text is discarded, never shown.

**Known limitation**: this sandboxed dev environment has outbound network
access to `api.anthropic.com` (confirmed reachable — a deliberately
invalid key correctly returns HTTP 401, not a connection failure) but no
`ANTHROPIC_API_KEY` is provisioned for the application to use. The
guardrail, facts-building, and orchestration are fully tested with the
LLM call mocked (`backend/tests/unit/test_ai_explanation_service.py`,
`backend/tests/api/test_ai_summary.py`); the live "available: true" path
has not been exercised end-to-end against the real API. Set
`ANTHROPIC_API_KEY` in `.env` to enable it — no code changes needed.

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
- **`/stress-test` is honest about what it can't model.** Four of the
  seven spec scenarios (interest rates, recession, INR depreciation,
  inflation) come back `available: false` with a specific `reason` —
  never a guessed sensitivity coefficient. The three that are computed
  say exactly what they're based on (`exposure_pct`: the fund's beta for
  an index shock, or its disclosed sector/market-cap weight for an
  exposure shock) so the number is always traceable to a real input.
  Every response also carries `hypothetical_notice`: these are
  illustrative scenarios, not predictions.

## Testing

`backend/tests/api/test_funds.py`, `test_portfolio.py`, `test_overlap.py`,
`test_portfolio_analysis.py`, `test_market_regime.py`, `test_stress_test.py`
and `test_ai_summary.py` run all of the above against the real Phase 2
seed data via FastAPI's `TestClient`: fund listing/search, full-detail
variant listings, each analytics endpoint's happy path, the explicit
insufficient-history path (10-year window against ~4 years of seed
history), top-holdings/HHI/allocation correctness (including the bonds'
"unclassified" case), pairwise overlap correctness and symmetry,
multi-fund combination correctness (hand-verified effective weights for a
3-fund mix, allocation reconciliation), per-regime behaviour correctness
(excess return reconciliation, summary text matching the sign of over/
underperformance), stress-scenario correctness (index/exposure impact
formulas reconciled against beta and disclosed allocation, all four macro
scenarios confirmed explicitly unavailable), the AI layer's "not
configured" path (live, no mocking needed) and its "available"/"discarded
fabrication" paths (LLM call mocked), and 404/422/400 error handling.
`backend/tests/unit/test_ai_explanation_service.py` unit-tests the
fabrication guardrail itself in isolation (number extraction, rounding
tolerance, exact and fabricated-number cases).
