"""Bridges the portfolio-combination analytics (analytics/portfolio.py) plus
the existing single-fund engines (concentration, overlap, correlation,
risk, drawdown) into the Phase 9 multi-fund Portfolio Analysis response.

Nothing here is a new financial formula — it's orchestration: combine each
fund's disclosed holdings and return series by portfolio weight, then run
the same deterministic functions already used for single-fund analysis
(Rule 5: reuse, don't duplicate).
"""
from __future__ import annotations

from itertools import combinations

import pandas as pd

from analytics.concentration import group_weights, herfindahl_hirschman_index, hhi_label, top_n_weight_pct
from analytics.correlation import return_correlation
from analytics.drawdown import max_drawdown
from analytics.overlap import overlap_label, weighted_overlap_pct
from analytics.portfolio import combine_effective_weights, combine_weighted_returns, synthetic_nav_from_returns
from analytics.risk import annualized_volatility, sharpe_ratio, sortino_ratio

UNCLASSIFIED_LABEL = "unclassified"
TOP_HOLDINGS_DISPLAY_COUNT = 10


def _sorted_allocation(totals: dict[str, float]) -> list[dict]:
    return [
        {"label": label, "weight_pct": round(weight, 4)}
        for label, weight in sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    ]


def compute_portfolio_analysis(
    fund_names: dict[int, str],
    fund_weights_pct: dict[int, float],
    per_fund_security_weights: dict[int, dict[str, float]],
    per_fund_sector_weights: dict[int, dict[str, float]],
    per_fund_mktcap_weights: dict[int, dict[str, float]],
    per_fund_returns: dict[int, pd.Series],
    risk_free_rate_annual: float,
) -> dict:
    fund_keys = {fid: str(fid) for fid in fund_names}
    weights_by_key = {fund_keys[fid]: w for fid, w in fund_weights_pct.items()}

    security_by_key = {fund_keys[fid]: w for fid, w in per_fund_security_weights.items()}
    sector_by_key = {fund_keys[fid]: w for fid, w in per_fund_sector_weights.items()}
    mktcap_by_key = {fund_keys[fid]: w for fid, w in per_fund_mktcap_weights.items()}

    combined_security = combine_effective_weights(security_by_key, weights_by_key)
    combined_sector = combine_effective_weights(sector_by_key, weights_by_key)
    combined_mktcap = combine_effective_weights(mktcap_by_key, weights_by_key)

    concentration = None
    top_holdings: list[dict] = []
    if combined_security:
        weights_list = list(combined_security.values())
        hhi = herfindahl_hirschman_index(weights_list)
        concentration = {
            "hhi": round(hhi, 2),
            "hhi_label": hhi_label(hhi),
            "top5_weight_pct": round(top_n_weight_pct(weights_list, 5), 4),
            "top10_weight_pct": round(top_n_weight_pct(weights_list, 10), 4),
        }
        ranked = sorted(combined_security.items(), key=lambda kv: kv[1], reverse=True)[:TOP_HOLDINGS_DISPLAY_COUNT]
        top_holdings = [
            {"rank": i, "security_name": name, "effective_weight_pct": round(weight, 4)}
            for i, (name, weight) in enumerate(ranked, start=1)
        ]

    pairwise_overlap = []
    for fid_a, fid_b in combinations(sorted(fund_names), 2):
        weights_a = per_fund_security_weights.get(fid_a)
        weights_b = per_fund_security_weights.get(fid_b)
        if not weights_a or not weights_b:
            continue
        overlap_pct = weighted_overlap_pct(weights_a, weights_b)
        pairwise_overlap.append({
            "fund_a_id": fid_a,
            "fund_a_name": fund_names[fid_a],
            "fund_b_id": fid_b,
            "fund_b_name": fund_names[fid_b],
            "weighted_overlap_pct": round(overlap_pct, 4),
            "overlap_label": overlap_label(overlap_pct),
        })

    correlations = []
    for fid_a, fid_b in combinations(sorted(per_fund_returns), 2):
        corr = return_correlation(per_fund_returns[fid_a], per_fund_returns[fid_b])
        if corr is not None:
            correlations.append(corr)
    average_pairwise_correlation = round(sum(correlations) / len(correlations), 4) if correlations else None

    risk_result = {"available": False, "reason": "insufficient_return_data",
                   "volatility_pct": None, "sharpe_ratio": None, "sortino_ratio": None, "observations_used": 0}
    drawdown_result = {"available": False, "reason": "insufficient_return_data",
                        "max_drawdown_pct": None, "peak_date": None, "trough_date": None,
                        "recovered": None, "recovery_date": None, "recovery_duration_days": None}

    missing_returns = set(fund_names) - set(per_fund_returns)
    if not missing_returns and len(per_fund_returns) >= 1:
        try:
            portfolio_returns = combine_weighted_returns(
                {fund_keys[fid]: series for fid, series in per_fund_returns.items()}, weights_by_key
            )
            if len(portfolio_returns) >= 2:
                risk_result = {
                    "available": True,
                    "reason": None,
                    "volatility_pct": round(annualized_volatility(portfolio_returns) * 100, 4),
                    "sharpe_ratio": _safe_ratio(sharpe_ratio, portfolio_returns, risk_free_rate_annual),
                    "sortino_ratio": _safe_ratio(sortino_ratio, portfolio_returns, risk_free_rate_annual),
                    "observations_used": len(portfolio_returns),
                }
                synthetic_nav = synthetic_nav_from_returns(portfolio_returns)
                dd = max_drawdown(synthetic_nav)
                drawdown_result = {
                    "available": True,
                    "reason": None,
                    "max_drawdown_pct": round(dd["max_drawdown_pct"] * 100, 4),
                    "peak_date": dd["peak_date"].date(),
                    "trough_date": dd["trough_date"].date(),
                    "recovered": dd["recovered"],
                    "recovery_date": dd["recovery_date"].date() if dd["recovery_date"] is not None else None,
                    "recovery_duration_days": dd["recovery_duration_days"],
                }
            else:
                risk_result["reason"] = "no_common_dates_across_funds"
                drawdown_result["reason"] = "no_common_dates_across_funds"
        except ValueError:
            pass  # leave the "insufficient_return_data" defaults

    return {
        "funds": [
            {"fund_id": fid, "scheme_name": fund_names[fid], "weight_pct": fund_weights_pct[fid]}
            for fid in fund_names
        ],
        "total_weight_pct": round(sum(fund_weights_pct.values()), 4),
        "combined_top_holdings": top_holdings,
        "sector_allocation": _sorted_allocation(combined_sector),
        "market_cap_allocation": _sorted_allocation(combined_mktcap),
        "concentration": concentration,
        "pairwise_overlap": pairwise_overlap,
        "average_pairwise_correlation": average_pairwise_correlation,
        "risk": risk_result,
        "drawdown": drawdown_result,
    }


def _safe_ratio(fn, returns: pd.Series, risk_free_rate_annual: float) -> float | None:
    try:
        return round(fn(returns, risk_free_rate_annual), 4)
    except ValueError:
        return None
