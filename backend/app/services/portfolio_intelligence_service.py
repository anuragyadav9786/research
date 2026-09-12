"""Bridges the concentration analytics engine (analytics/concentration.py)
to the Portfolio DNA / concentration API response shape — same pattern as
fund_analytics_service.py: this module decides presentation (rounding,
sorting, "no data" fallbacks), analytics/ stays pure.
"""
from __future__ import annotations

from app.repositories.portfolio_repository import HoldingRow
from analytics.concentration import (
    group_weights,
    herfindahl_hirschman_index,
    hhi_label,
    top_n_weight_pct,
)

UNCLASSIFIED_LABEL = "unclassified"
TOP_HOLDINGS_DISPLAY_COUNT = 10


def _sorted_allocation(totals: dict[str, float]) -> list[dict]:
    return [
        {"label": label, "weight_pct": round(weight, 4)}
        for label, weight in sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    ]


def compute_portfolio_dna(holdings: list[HoldingRow]) -> dict:
    if not holdings:
        return {
            "available": False,
            "reason": "no_holdings_data",
            "as_of_date": None,
            "source_name": None,
            "total_holdings": 0,
            "total_disclosed_weight_pct": None,
            "top_holdings": [],
            "top5_weight_pct": None,
            "top10_weight_pct": None,
            "hhi": None,
            "hhi_label": None,
            "sector_allocation": [],
            "market_cap_allocation": [],
        }

    weights = [h.weight_pct for h in holdings]
    hhi = herfindahl_hirschman_index(weights)

    sector_totals = group_weights([(h.sector_name or UNCLASSIFIED_LABEL, h.weight_pct) for h in holdings])
    market_cap_totals = group_weights(
        [(h.market_cap_category or UNCLASSIFIED_LABEL, h.weight_pct) for h in holdings]
    )

    top_holdings = sorted(holdings, key=lambda h: h.weight_pct, reverse=True)[:TOP_HOLDINGS_DISPLAY_COUNT]

    return {
        "available": True,
        "reason": None,
        "total_holdings": len(holdings),
        "total_disclosed_weight_pct": round(sum(weights), 4),
        "top_holdings": [
            {
                "rank": i,
                "security_name": h.security_name,
                "sector": h.sector_name,
                "market_cap_category": h.market_cap_category,
                "weight_pct": h.weight_pct,
            }
            for i, h in enumerate(top_holdings, start=1)
        ],
        "top5_weight_pct": round(top_n_weight_pct(weights, 5), 4),
        "top10_weight_pct": round(top_n_weight_pct(weights, 10), 4),
        "hhi": round(hhi, 2),
        "hhi_label": hhi_label(hhi),
        "sector_allocation": _sorted_allocation(sector_totals),
        "market_cap_allocation": _sorted_allocation(market_cap_totals),
    }
