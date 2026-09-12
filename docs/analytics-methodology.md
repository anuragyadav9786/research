# ThinkFin Analytics Methodology

Every metric below is implemented as a pure, deterministic Python function in
`analytics/` (repo root) — never calculated by an LLM (Rule 4). Each function
carries the same Definition/Formula/Input/Methodology/Interpretation/
Limitations documentation inline as a docstring; this file consolidates it
in one place and adds the cross-cutting assumptions that apply across
functions.

All functions are unit-tested in `backend/tests/analytics/` against
independently hand-computed reference values (see "Testing approach" below).

## Cross-cutting assumptions

| Assumption | Value | Where configured |
|---|---|---|
| Trading periods per year | 252 | `analytics/risk.PERIODS_PER_YEAR` |
| Risk-free rate (annual, decimal) | `Settings.risk_free_rate` (currently a placeholder `0.07`) | `backend/app/core/config.py` |
| Year length for CAGR | 365.25 days | `analytics/returns.py`, `analytics/rolling_returns.py` |

The risk-free rate is a **documented placeholder**, not an ingested value —
see `docs/BUILD_PLAN.md` open decision #4 (RBI 91-day T-bill rate is the
intended real source; not yet wired up). Every Sharpe/Sortino figure the
platform reports should be read as "assuming a 7% annual risk-free rate"
until that's replaced with a real feed and this document is updated.

## Returns (`analytics/returns.py`)

**CAGR** — Compound Annual Growth Rate
- Formula: `(nav_end / nav_start) ** (1/years) - 1`
- Input: start/end NAV, elapsed years (fractional allowed)
- Interpretation: the constant annual rate that reproduces the observed
  total return; use for any period > 1 year.
- Limitations: undefined for `years <= 0` or `nav_start <= 0`; unstable for
  sub-annual periods (use `simple_return` instead).

**Simple return** — point-to-point, non-annualized: `nav_end/nav_start - 1`.

## Rolling returns (`analytics/rolling_returns.py`)

- Definition: the distribution of CAGR outcomes across every historically
  possible entry date for a given holding period (e.g. "every 3-year hold").
- Methodology: window length in calendar days (`round(years * 365.25)`),
  end date matched to the last available NAV on/before the target date.
- Distribution stats reported: min, p10, p25, median, p75, p90, max
  (numpy linear-interpolation percentiles).
- Benchmark consistency: aligns fund and benchmark rolling series on shared
  start dates, then reports beat-rate %, average/median excess return, and
  the single worst relative-performance window.
- Limitation: an empty result means "not enough history for this window,"
  not zero performance — must be surfaced as such in the UI, never as a
  blank chart with no explanation.

## Risk & survival (`analytics/risk.py`, `analytics/drawdown.py`, `analytics/capture_ratio.py`, `analytics/alpha_beta.py`)

**Annualized volatility**: `std(daily_returns, ddof=1) * sqrt(252)`.

**Downside deviation**: `sqrt(mean(min(r - target, 0)^2)) * sqrt(252)` —
only sub-target returns contribute.

**Sharpe ratio**: `mean(daily_returns - daily_rf) / std(daily_returns) *
sqrt(252)`, where the annual risk-free rate is converted to a
compounding-consistent daily rate (`(1+rf)^(1/252) - 1`), not simply
divided by 252.

**Sortino ratio**: `(mean(daily_returns) - daily_rf) * 252 /
downside_deviation(daily_returns, target=daily_rf)`. The risk-free rate is
used both as the return being exceeded and as the downside-deviation
target — a documented, common but not universal, convention.

**Maximum drawdown**: worst peak-to-trough decline, with the specific peak
date, trough date, recovery date (or explicit "not yet recovered"), and
recovery duration in days. Identifies exactly the single worst episode, not
every drawdown in the series.

**Upside/Downside capture ratio**: geometrically compounded fund return
divided by geometrically compounded benchmark return, restricted to
benchmark-positive (upside) or benchmark-negative (downside) periods,
expressed as a percentage. Returns `None` — never a fabricated 0 or 100 —
when the sample contains no periods of the relevant sign.

**Beta**: `Cov(fund, benchmark) / Var(benchmark)` over dates present in
both series. Single-factor market beta only — no sector/size/style
decomposition (see the later Fund Manager Skill Engine phase for that).

**Jensen's alpha**: `fund_return - [rf + beta*(benchmark_return - rf)]`,
computed from already-annualized returns and a computed beta. Positive
means the fund outperformed what its market exposure (beta) alone would
predict via CAPM — not a claim that a manager's stock-picking specifically
caused the excess.

## Concentration (`analytics/concentration.py`)

**Herfindahl-Hirschman Index (HHI)**: `sum((weight_pct_i / 100)^2) * 10000`.
The standard 0-10000 HHI scale, the same one used in US DOJ/FTC merger
antitrust analysis, applied here to portfolio weights instead of market
shares. A portfolio of N equal-weight holdings has `HHI = 10000/N`.
Labelled `diversified` (<1500), `moderate_concentration` (1500-2500), or
`high_concentration` (>=2500) — the DOJ/FTC thresholds, reused by
convention, not derived from portfolio-specific research. Understates true
concentration if the input weights don't sum close to 100% (e.g. only
top-holdings are disclosed) — always shown alongside total disclosed
weight so this is visible, never hidden.

**Top-N weight**: sum of the N largest holding weights (e.g. "top 5
holdings = X% of the portfolio"). Sums all holdings if there are fewer
than N — not an error, just a small/concentrated portfolio.

**Group weights**: a generic groupby-sum used for both sector allocation
and market-cap allocation — there's nothing holdings-specific about
"total weight per category."

Market-cap category (`securities.market_cap_category`) is presently only
populated for the Phase 2 synthetic sample securities, assigned by the
same "clearly-labelled fictional data" logic as the rest of that seed —
see `database/seeds/seed_sample_data.py`'s header. It is `null` for bonds
and other non-equity instruments, and for any real security not yet
classified — grouped under "unclassified" rather than guessed.

## Overlap & correlation (`analytics/overlap.py`, `analytics/correlation.py`)

**Weighted overlap**: `sum(min(weight_a[label], weight_b[label]) for label
in union(weights_a, weights_b))`. The standard fund-research "portfolio
overlap" methodology — only the smaller of the two weights counts per
holding, since that's the exposure genuinely shared by both. Generic over
any label set: the same function computes security-level overlap or
sector-level overlap (`sector_overlap_pct` in the API is literally
`weighted_overlap_pct` applied to sector-aggregated weights instead of
per-security weights).

**Overlap label**: `<20%` low, `20-50%` moderate, `>=50%` high. Unlike
HHI's DOJ/FTC thresholds, **there is no official regulatory standard for
portfolio overlap** — these are a commonly cited practitioner rule of
thumb, documented here as exactly that (an explicit "uncertain
methodology, documented rather than guessed" case per the project's
financial-methodology rule), not a precise cutoff backed by regulation.

**Return correlation**: standard Pearson correlation coefficient (`numpy.
corrcoef`) between two funds' daily NAV returns, aligned on common dates
only. Complements weighted overlap rather than replacing it — two funds
can hold entirely different stocks yet have highly correlated returns
(both quietly tracking the same market), or the reverse. Uses each
scheme's direct/growth NAV series by default (falls back to whichever
variant exists) since holdings-based overlap doesn't depend on plan/
option and a single representative return series is sufficient for this
purpose — see `fund_repository.get_default_variant`.

## Multi-fund portfolio combination (`analytics/portfolio.py`)

**Combine effective weights**: `effective_weight[label] = sum_over_funds(
fund_weight_pct/100 * per_fund_weight[fund].get(label, 0))`. The
"look-through" formula: how much of the *overall portfolio* each security
(or sector, or market-cap bucket — it's generic over the label) actually
represents once each fund's own weight in the portfolio is accounted for.
This is precisely how hidden cross-fund concentration becomes visible: two
funds that each look diversified individually can combine into a
portfolio that isn't, and this arithmetic is what surfaces that.

**Combine weighted returns**: `portfolio_return[t] = sum(fund_weight_pct/
100 * fund_return[t])`, restricted to dates present in every constituent
fund's history (inner join — documented limitation: a fund with a shorter
history shrinks the analyzable window for the whole portfolio) and
assuming static weights throughout (no rebalancing modeled — a real
portfolio drifts from target weights as constituent funds move; this
does not simulate that drift).

**Synthetic NAV from returns**: `nav[t] = base * prod(1 + returns[<=t])`
— reconstructs a NAV-like level series purely so the existing
`analytics.drawdown.max_drawdown` can run on a combined portfolio without
a second drawdown implementation. It's a hypothetical ₹`base` investment
growing at exactly the combined return series, not a real instrument.

Portfolio-level volatility/Sharpe/Sortino reuse `analytics/risk.py`
directly on the combined return series — no separate portfolio-risk
formulas exist, by design (Rule 5: don't duplicate).

## Testing approach

Each module has a corresponding `backend/tests/analytics/test_*.py` file.
Reference values are computed one of three ways, in order of preference:
1. **Independent library** — e.g. `annualized_volatility` is checked against
   Python's stdlib `statistics.stdev`, not the analytics module's own
   internals.
2. **Deterministic construction** — e.g. rolling returns are tested against
   a NAV series built from a known constant daily growth rate, so the
   correct answer is derivable by hand from the construction, not just
   plausible-looking.
3. **Hand-computed arithmetic** — for formulas with no independent library
   equivalent (Sharpe, Sortino, capture ratios, Jensen's alpha), the test
   computes the expected value via the same documented formula using plain
   Python arithmetic, checking the implementation is a faithful, bug-free
   transcription of the documented method — plus edge cases (zero variance,
   no matching periods, insufficient observations) that must raise or
   return `None` rather than a misleading number.

Run with: `cd backend && source .venv/bin/activate && pytest tests/analytics -q`
