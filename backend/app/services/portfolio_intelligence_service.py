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


def _weighted_average_ytm(holdings: list[HoldingRow]) -> float | None:
    """Portfolio-level YTM, weighted by each holding's weight_pct — only
    meaningful over debt/money-market holdings, which are the only ones
    a real disclosure ever states a YTM for (equity rows carry `None`).
    `None` when no holding in this portfolio has a YTM at all, rather
    than a misleading 0."""
    rated = [h for h in holdings if h.ytm_pct is not None]
    if not rated:
        return None
    total_weight = sum(h.weight_pct for h in rated)
    if total_weight == 0:
        return None
    return sum(h.ytm_pct * h.weight_pct for h in rated) / total_weight


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
            "instrument_type_allocation": [],
            "credit_quality_allocation": [],
            "credit_quality_coverage_pct": None,
            "average_ytm_pct": None,
        }

    weights = [h.weight_pct for h in holdings]
    hhi = herfindahl_hirschman_index(weights)

    sector_totals = group_weights([(h.sector_name or UNCLASSIFIED_LABEL, h.weight_pct) for h in holdings])
    market_cap_totals = group_weights(
        [(h.market_cap_category or UNCLASSIFIED_LABEL, h.weight_pct) for h in holdings]
    )
    instrument_type_totals = group_weights(
        [(h.instrument_type or UNCLASSIFIED_LABEL, h.weight_pct) for h in holdings]
    )
    rated_holdings = [h for h in holdings if h.credit_rating is not None]
    credit_quality_totals = group_weights([(h.credit_rating, h.weight_pct) for h in rated_holdings])
    credit_quality_coverage_pct = round(sum(h.weight_pct for h in rated_holdings), 4) if rated_holdings else None

    top_holdings = sorted(holdings, key=lambda h: h.weight_pct, reverse=True)[:TOP_HOLDINGS_DISPLAY_COUNT]
    average_ytm = _weighted_average_ytm(holdings)

    return {
        "available": True,
        "reason": None,
        "total_holdings": len(holdings),
        "total_disclosed_weight_pct": round(sum(weights), 4),
        "top_holdings": [
            {
                "rank": i,
                "security_id": h.security_id,
                "security_name": h.security_name,
                "sector": h.sector_name,
                "market_cap_category": h.market_cap_category,
                "instrument_type": h.instrument_type,
                "credit_rating": h.credit_rating,
                "ytm_pct": h.ytm_pct,
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
        "instrument_type_allocation": _sorted_allocation(instrument_type_totals),
        "credit_quality_allocation": _sorted_allocation(credit_quality_totals),
        "credit_quality_coverage_pct": credit_quality_coverage_pct,
        "average_ytm_pct": round(average_ytm, 3) if average_ytm is not None else None,
    }
