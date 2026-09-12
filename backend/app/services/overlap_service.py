"""Bridges the overlap/correlation analytics engine to the Phase 8 API
response shape — same pattern as the other *_intelligence_service modules:
this decides presentation, analytics/ stays pure.
"""
from __future__ import annotations

from app.repositories.portfolio_repository import HoldingRow
from analytics.concentration import group_weights
from analytics.correlation import return_correlation
from analytics.overlap import overlap_counts, overlap_label, weighted_overlap_pct

UNCLASSIFIED_LABEL = "unclassified"


def _holdings_to_weights(holdings: list[HoldingRow]) -> dict[str, float]:
    return {h.security_name: h.weight_pct for h in holdings}


def _sector_weights(holdings: list[HoldingRow]) -> dict[str, float]:
    return group_weights([(h.sector_name or UNCLASSIFIED_LABEL, h.weight_pct) for h in holdings])


def compute_overlap(
    holdings_a: list[HoldingRow],
    holdings_b: list[HoldingRow],
    returns_a,
    returns_b,
) -> dict:
    if not holdings_a or not holdings_b:
        return {
            "available": False,
            "reason": "no_holdings_data",
            "common_securities_count": 0,
            "only_in_a_count": 0,
            "only_in_b_count": 0,
            "weighted_overlap_pct": None,
            "sector_overlap_pct": None,
            "overlap_label": None,
            "return_correlation": None,
            "common_holdings": [],
            "sector_detail": [],
        }

    weights_a = _holdings_to_weights(holdings_a)
    weights_b = _holdings_to_weights(holdings_b)
    sector_a = _sector_weights(holdings_a)
    sector_b = _sector_weights(holdings_b)

    counts = overlap_counts(weights_a, weights_b)
    weighted_overlap = weighted_overlap_pct(weights_a, weights_b)
    sector_overlap = weighted_overlap_pct(sector_a, sector_b)

    common_holdings = [
        {
            "security_name": name,
            "weight_a": round(weights_a[name], 4),
            "weight_b": round(weights_b[name], 4),
            "min_weight": round(min(weights_a[name], weights_b[name]), 4),
        }
        for name in (set(weights_a) & set(weights_b))
    ]
    common_holdings.sort(key=lambda h: h["min_weight"], reverse=True)

    sector_detail = [
        {
            "sector": sector,
            "weight_a": round(sector_a.get(sector, 0.0), 4),
            "weight_b": round(sector_b.get(sector, 0.0), 4),
            "min_weight": round(min(sector_a.get(sector, 0.0), sector_b.get(sector, 0.0)), 4),
        }
        for sector in (set(sector_a) | set(sector_b))
    ]
    sector_detail.sort(key=lambda s: s["min_weight"], reverse=True)

    correlation = return_correlation(returns_a, returns_b) if returns_a is not None and returns_b is not None else None

    return {
        "available": True,
        "reason": None,
        "common_securities_count": counts["common"],
        "only_in_a_count": counts["only_in_a"],
        "only_in_b_count": counts["only_in_b"],
        "weighted_overlap_pct": round(weighted_overlap, 4),
        "sector_overlap_pct": round(sector_overlap, 4),
        "overlap_label": overlap_label(weighted_overlap),
        "return_correlation": round(correlation, 4) if correlation is not None else None,
        "common_holdings": common_holdings,
        "sector_detail": sector_detail,
    }
