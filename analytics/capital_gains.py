"""Capital-gains tax classification for still-OPEN FIFO lots (analytics/
cost_basis.py's `Lot`): what LTCG/STCG tax would apply if each lot were
sold TODAY, under India's mutual-fund capital-gains rules. A factual
"if sold today" statement only — never a suggestion to sell, same
no-advice discipline app/services/cas_insights_service.py follows.

Scope: only still-held lots. A lot already sold in the past was taxed
under whatever rules applied on its actual sale date (which can differ
from today's — e.g. equity LTCG was 10% before 23 July 2024) — that
historical liability is out of scope here.

Equity-vs-debt classification for TAX purposes is a different question
from the platform's general asset-class display classification
(data_pipeline/normalization/category_classification.py), which never
estimates a percentage from a category string. Tax law turns on whether a
scheme is "equity oriented" (>=65% domestic equity) — and that IS
knowable without guessing for schemes in SEBI's standard categories,
because SEBI's Oct-2017 scheme-categorization circular sets a regulatory
MINIMUM equity allocation per "Equity Scheme" sub-category (all >=65%,
several >=80%) and caps "Debt Scheme" categories at ~0% equity. Three
Hybrid sub-types are also regulatorily pinned for this purpose:
Aggressive Hybrid (65-80% equity) and Arbitrage/Equity Savings Funds
(>=65% gross equity exposure, even though market-neutral/hedged) are
equity-oriented by the same tax definition; Conservative Hybrid (10-25%)
and Balanced Hybrid (40-60%) are not. Everything else — Dynamic Asset
Allocation/Balanced Advantage (allocation floats 0-100% day to day),
Multi Asset Allocation, Gold/Other/Index/ETF/FoF, Solution Oriented, or
any category string not recognized here — is reported "indeterminate":
the lot's gain and holding period are still shown, but no tax rate is
assigned without a basis, same rule classify_equity_style already
follows for an unrecognized equity sub-category.

Current rates (effective 23 July 2024; re-checked via web search on
2026-11-03 and confirmed unchanged by both Budget 2025 and Budget 2026 —
see sources below). Re-verify after any future Union Budget before
trusting this module's output:

- Equity-oriented: held <=12 months -> STCG @ 20%; >12 months -> LTCG
  @ 12.5%. LTCG carries an aggregate Rs. 1.25 lakh/year EXEMPTION across
  ALL of an investor's equity LTCG for the year (not per lot, not per
  scheme) — this module has no visibility into gains outside this
  portfolio, so `tax_if_realized_today` is reported pre-exemption, and
  the exemption is surfaced once as a note at the portfolio level
  (see summarize_capital_gains), never silently subtracted.
- Debt-oriented, units acquired on/after 1 Apr 2023: taxed at the
  investor's income-tax SLAB rate regardless of holding period. This
  module doesn't know the investor's slab, so `applicable_rate_pct` and
  `tax_if_realized_today` are left null — `tax_basis` says why.
- Debt-oriented, units acquired before 1 Apr 2023: held >24 months ->
  LTCG @ 12.5% (no indexation); <=24 months -> slab rate (same null
  caveat).

Cess/surcharge are never added — they depend on the investor's total
income across all sources, entirely outside this ledger's visibility.

Sources (checked 2026-11-03): the 23-July-2024 Finance Act change
(equity LTCG 10%->12.5%, STCG 15%->20%, debt-fund indexation removed,
pre-Apr-2023 debt LTCG holding period 36->24 months) is consistently
reported by policybazaar.com/mutual-funds/tax-on-mutual-funds,
cleartax.in/s/tax-on-debt-funds, and bajajfinserv.in's LTCG explainer;
"no change" for Budget 2025 is reported by businesstoday.in's
2025-02-03 post-budget explainer; "no change" for Budget 2026 is
reported by angelone.in's 2026-02-01 coverage. These are secondary
sources, not the Finance Act text itself — treat this the way
docs/data-sources.md treats every other external fact: accurate as of
the stated check date, not a live feed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from analytics.cost_basis import Lot
from data_pipeline.normalization.category_classification import classify_asset_class

TAX_ORIENTATION_EQUITY = "equity_oriented"
TAX_ORIENTATION_DEBT = "debt_oriented"
TAX_ORIENTATION_INDETERMINATE = "indeterminate"

_EQUITY_LTCG_HOLDING_DAYS = 365  # ">12 months" treated as >365 days, matching _HOLDING_PERIOD_BUCKETS' own convention
_DEBT_PRE_APR2023_LTCG_HOLDING_DAYS = 365 * 2  # ">24 months"
_DEBT_REGIME_CUTOVER = date(2023, 4, 1)

EQUITY_STCG_RATE_PCT = 20.0
EQUITY_LTCG_RATE_PCT = 12.5
DEBT_PRE_APR2023_LTCG_RATE_PCT = 12.5

EQUITY_LTCG_ANNUAL_EXEMPTION_NOTE = (
    "Equity LTCG tax above is shown before the Rs. 1,25,000/year aggregate exemption, which applies across "
    "all of your equity LTCG for the financial year (not per lot or per scheme) — not netted off here, since "
    "this tool has no visibility into capital gains outside this portfolio."
)
_SLAB_RATE_BASIS = (
    "Debt-oriented: taxed at your income-tax slab rate (units acquired on/after 1 Apr 2023, or held <=24 months "
    "if acquired earlier) — this tool doesn't know your slab rate, so no amount is shown."
)
_INDETERMINATE_BASIS = (
    "This scheme's stated category doesn't pin down a regulatory-minimum equity allocation one way or the "
    "other (e.g. Balanced Advantage/Dynamic Asset Allocation, Multi Asset, Gold, Other/Index/ETF/FoF) — not "
    "guessed, so no tax classification is shown."
)

_EQUITY_ORIENTED_HYBRID_PATTERN = re.compile(r"aggressive\s+hybrid|arbitrage|equity\s+savings", re.IGNORECASE)
_DEBT_ORIENTED_HYBRID_PATTERN = re.compile(r"conservative\s+hybrid|balanced\s+hybrid\b", re.IGNORECASE)


def classify_tax_orientation(category: str) -> str:
    """Whether a scheme is "equity oriented" for capital-gains tax purposes
    — a regulatory question, not this scheme's actual current allocation,
    which this function never inspects or estimates."""
    asset_class = classify_asset_class(category)
    if asset_class == "Equity":
        return TAX_ORIENTATION_EQUITY
    if asset_class == "Debt":
        return TAX_ORIENTATION_DEBT
    if asset_class == "Hybrid":
        if _EQUITY_ORIENTED_HYBRID_PATTERN.search(category):
            return TAX_ORIENTATION_EQUITY
        if _DEBT_ORIENTED_HYBRID_PATTERN.search(category):
            return TAX_ORIENTATION_DEBT
    return TAX_ORIENTATION_INDETERMINATE


@dataclass
class LotGainClassification:
    purchase_date: date
    units: float
    current_value: float
    unrealized_gain: float
    holding_period_days: int
    tax_orientation: str
    classification: str | None  # "LTCG" / "STCG" / None if not determinable
    applicable_rate_pct: float | None
    tax_if_realized_today: float | None
    tax_basis: str  # always present, explains the classification or the lack of one


def classify_lot_gain(lot: Lot, as_of: date, current_nav: float, tax_orientation: str) -> LotGainClassification:
    current_value = lot.units * current_nav
    unrealized_gain = current_value - lot.cost
    holding_days = (as_of - lot.purchase_date).days
    taxable_gain = max(unrealized_gain, 0.0)  # a loss has nothing to tax today; it isn't realized

    classification: str | None = None
    rate: float | None = None
    tax: float | None = None

    if tax_orientation == TAX_ORIENTATION_EQUITY:
        if holding_days > _EQUITY_LTCG_HOLDING_DAYS:
            classification, rate = "LTCG", EQUITY_LTCG_RATE_PCT
            basis = "Equity-oriented, held >12 months: LTCG @ 12.5% (before the annual exemption — see portfolio note)"
        else:
            classification, rate = "STCG", EQUITY_STCG_RATE_PCT
            basis = "Equity-oriented, held <=12 months: STCG @ 20%"
        tax = taxable_gain * (rate / 100)
    elif tax_orientation == TAX_ORIENTATION_DEBT:
        if lot.purchase_date < _DEBT_REGIME_CUTOVER and holding_days > _DEBT_PRE_APR2023_LTCG_HOLDING_DAYS:
            classification, rate = "LTCG", DEBT_PRE_APR2023_LTCG_RATE_PCT
            basis = "Debt-oriented, acquired before 1 Apr 2023 and held >24 months: LTCG @ 12.5% (no indexation)"
            tax = taxable_gain * (rate / 100)
        else:
            basis = _SLAB_RATE_BASIS
    else:
        basis = _INDETERMINATE_BASIS

    return LotGainClassification(
        purchase_date=lot.purchase_date,
        units=round(lot.units, 4),
        current_value=round(current_value, 2),
        unrealized_gain=round(unrealized_gain, 2),
        holding_period_days=holding_days,
        tax_orientation=tax_orientation,
        classification=classification,
        applicable_rate_pct=rate,
        tax_if_realized_today=round(tax, 2) if tax is not None else None,
        tax_basis=basis,
    )


def summarize_capital_gains(lot_classifications: list[LotGainClassification]) -> dict:
    """Portfolio/scheme-level roll-up, grouped by how each lot was (or
    wasn't) classified. `tax_if_realized_today` on the summary sums only
    the buckets with an actual computable amount (STCG/LTCG) — it is
    never a total tax liability figure, since slab-dependent and
    indeterminate lots have a real but unquantifiable tax here."""
    buckets = ("STCG", "LTCG", "slab_rate_dependent", "indeterminate")
    by_bucket: dict[str, dict] = {b: {"lot_count": 0, "unrealized_gain": 0.0, "tax_if_realized_today": 0.0} for b in buckets}

    for lc in lot_classifications:
        if lc.classification == "STCG":
            bucket = "STCG"
        elif lc.classification == "LTCG":
            bucket = "LTCG"
        elif lc.tax_orientation == TAX_ORIENTATION_DEBT:
            bucket = "slab_rate_dependent"
        else:
            bucket = "indeterminate"
        by_bucket[bucket]["lot_count"] += 1
        by_bucket[bucket]["unrealized_gain"] += lc.unrealized_gain
        by_bucket[bucket]["tax_if_realized_today"] += lc.tax_if_realized_today or 0.0

    for bucket_summary in by_bucket.values():
        bucket_summary["unrealized_gain"] = round(bucket_summary["unrealized_gain"], 2)
        bucket_summary["tax_if_realized_today"] = round(bucket_summary["tax_if_realized_today"], 2)

    return {
        "by_bucket": by_bucket,
        "total_tax_if_realized_today": round(by_bucket["STCG"]["tax_if_realized_today"] + by_bucket["LTCG"]["tax_if_realized_today"], 2),
        "equity_ltcg_exemption_note": EQUITY_LTCG_ANNUAL_EXEMPTION_NOTE if by_bucket["LTCG"]["lot_count"] > 0 else None,
        "lots": [
            {
                "purchase_date": lc.purchase_date,
                "units": lc.units,
                "current_value": lc.current_value,
                "unrealized_gain": lc.unrealized_gain,
                "holding_period_days": lc.holding_period_days,
                "classification": lc.classification,
                "applicable_rate_pct": lc.applicable_rate_pct,
                "tax_if_realized_today": lc.tax_if_realized_today,
                "tax_basis": lc.tax_basis,
            }
            for lc in lot_classifications
        ],
    }
