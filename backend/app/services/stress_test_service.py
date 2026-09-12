"""Bridges the stress-testing analytics (analytics/stress_testing.py) to
the Phase 11 API response — orchestration and presentation only; the
formulas themselves live in analytics/ per Rule 4.
"""
from __future__ import annotations

from analytics.stress_testing import SCENARIOS, exposure_shock_impact_pct, index_shock_impact_pct


def _find_sector_exposure(sector_allocation: dict[str, float], target: str) -> float:
    target_lower = target.lower()
    for label, weight in sector_allocation.items():
        if target_lower in label.lower():
            return weight
    return 0.0


def run_stress_test(
    fund_beta: float | None,
    sector_allocation: dict[str, float] | None,
    market_cap_allocation: dict[str, float] | None,
) -> list[dict]:
    results = []

    for scenario in SCENARIOS:
        base = {
            "scenario_id": scenario["id"],
            "name": scenario["name"],
            "description": scenario["description"],
            "shock_type": scenario["shock_type"],
            "shock_pct": scenario.get("shock_pct"),
        }

        if scenario["shock_type"] == "unmodeled":
            results.append({
                **base, "available": False, "reason": scenario["reason"],
                "exposure_pct": None, "estimated_impact_pct": None,
            })
            continue

        if scenario["shock_type"] == "index":
            if fund_beta is None:
                results.append({
                    **base, "available": False,
                    "reason": "Fund beta could not be computed (insufficient NAV/benchmark history).",
                    "exposure_pct": None, "estimated_impact_pct": None,
                })
            else:
                impact = index_shock_impact_pct(fund_beta, scenario["shock_pct"])
                results.append({
                    **base, "available": True, "reason": None,
                    "exposure_pct": round(fund_beta, 4), "estimated_impact_pct": round(impact, 4),
                })
            continue

        # sector or market_cap shock
        allocation = sector_allocation if scenario["shock_type"] == "sector" else market_cap_allocation
        if allocation is None:
            results.append({
                **base, "available": False,
                "reason": "No portfolio holdings data available for this fund.",
                "exposure_pct": None, "estimated_impact_pct": None,
            })
            continue

        exposure = (
            _find_sector_exposure(allocation, scenario["target"])
            if scenario["shock_type"] == "sector"
            else allocation.get(scenario["target"], 0.0)
        )
        impact = exposure_shock_impact_pct(exposure, scenario["shock_pct"])
        results.append({
            **base, "available": True, "reason": None,
            "exposure_pct": round(exposure, 4), "estimated_impact_pct": round(impact, 4),
        })

    return results
