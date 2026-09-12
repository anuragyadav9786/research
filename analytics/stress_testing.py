"""Stress-Test Engine (Section 14).

These are hypothetical scenarios, not predictions — the module docstring
on every function below and the `disclaimer`/`hypothetical_notice` fields
on the API response say so explicitly, per Rule 2/4 and Section 33.

Honesty about what can and can't be modeled matters more here than
anywhere else in the codebase: three of the seven scenarios named in the
product spec (a broad-market decline, a market-cap-segment decline, a
sector decline) map cleanly onto data this platform actually has (a
fund's beta to its benchmark, and its disclosed sector/market-cap
exposure from Phase 7). The other four (interest rates, recession, INR
depreciation, inflation) would need real factor-sensitivity data — bond
duration, currency exposure, a macro factor model — that doesn't exist
yet. Rather than inventing plausible-sounding sensitivity coefficients
for those, they are marked `shock_type="unmodeled"` with an explicit
reason. This is the project's own rule in action: "when uncertain about
financial methodology, don't guess — document the uncertainty."
"""
from __future__ import annotations

SCENARIOS = [
    {
        "id": "broad_market_down_25",
        "name": "Broad Market Falls 25%",
        "shock_type": "index",
        "shock_pct": -25.0,
        "description": (
            "A sharp, broad decline in the fund's benchmark index (e.g. Nifty 50 falling "
            "25% for a large-cap equity fund) — estimated via the fund's beta to that benchmark."
        ),
    },
    {
        "id": "midcap_down_40",
        "name": "Midcaps Fall 40%",
        "shock_type": "market_cap",
        "target": "mid_cap",
        "shock_pct": -40.0,
        "description": "A severe selloff concentrated in mid-cap stocks, estimated via the fund's disclosed mid-cap exposure.",
    },
    {
        "id": "it_sector_down_30",
        "name": "IT Sector Falls 30%",
        "shock_type": "sector",
        "target": "information technology",
        "shock_pct": -30.0,
        "description": "A sharp decline in the IT sector, estimated via the fund's disclosed IT sector exposure.",
    },
    {
        "id": "rates_up_sharply",
        "name": "Interest Rates Rise Sharply",
        "shock_type": "unmodeled",
        "reason": "No interest-rate duration/sensitivity data is captured for holdings yet.",
        "description": "A sharp rise in interest rates, which would primarily affect debt holdings via duration.",
    },
    {
        "id": "recession",
        "name": "Recession",
        "shock_type": "unmodeled",
        "reason": "No macro factor model (growth sensitivity, earnings-cycle exposure) exists yet.",
        "description": "A broad economic contraction affecting corporate earnings across sectors.",
    },
    {
        "id": "inr_depreciation",
        "name": "INR Depreciates Significantly",
        "shock_type": "unmodeled",
        "reason": "No currency/FX exposure data is captured for holdings yet.",
        "description": "A sharp fall in the Indian Rupee, which would affect funds with foreign currency exposure or import/export-sensitive holdings.",
    },
    {
        "id": "inflation_shock",
        "name": "Inflation Shock",
        "shock_type": "unmodeled",
        "reason": "No inflation-sensitivity factor model exists yet.",
        "description": "A sudden, sharp rise in inflation, which affects sectors and bond durations differently.",
    },
]


def index_shock_impact_pct(beta: float, shock_pct: float) -> float:
    """Estimated fund impact from a shock to its benchmark index.

    Formula: impact_pct = beta * shock_pct

    This is the standard first-order CAPM approximation: a fund with
    beta B is expected to move approximately B times as much as its
    benchmark. Documented limitations: assumes the linear beta
    relationship — estimated from ordinary historical daily returns —
    continues to hold during an extreme, discontinuous move, which real
    market stress events often violate (correlations and volatility both
    tend to rise in a crisis, a phenomenon beta estimated in calm periods
    does not capture). This is a first approximation, not a crisis model.
    """
    return beta * shock_pct


def exposure_shock_impact_pct(exposure_weight_pct: float, shock_pct: float) -> float:
    """Estimated fund impact from a shock isolated to one sector or
    market-cap segment the fund is exposed to.

    Formula: impact_pct = (exposure_weight_pct / 100) * shock_pct

    Assumes the shock is contained to the named segment and every other
    holding is unaffected — a documented simplification. Real sector/
    market-cap shocks typically have spillover effects on other segments
    (e.g. a severe IT selloff can drag down broader market sentiment);
    this model does not capture contagion, only the fund's direct,
    isolated exposure to the shocked segment.
    """
    return (exposure_weight_pct / 100.0) * shock_pct
