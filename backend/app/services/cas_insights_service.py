"""Portfolio Analysis §"Actionable Insights" + "Portfolio Health Check" —
the final synthesis layer over everything Phases 1-9 already computed.

Ground rules, taken directly from the module's own spec and enforced
throughout every rule below:
  - Never a buy/sell/hold recommendation. Every insight states a fact
    already computed elsewhere in this module (a concentration number,
    an overlap percentage, a data-completeness gap) — never "you should."
  - Never alarmist language. Severity labels are the neutral, clinical
    "informational" / "notable" / "significant" — never "warning",
    "danger", "critical", or similar. No insight is emitted from a
    financial forecast or a guess about intent (see cas_portfolio_
    service.py's own docstring on why "return-chasing" detection is out
    of scope entirely, for the same reason).
  - Nothing here is a new calculation. Every rule reads a number some
    earlier phase already computed and cites it back — this module's
    only job is to decide which already-computed facts are worth
    surfacing, and how severely, using thresholds/labels this codebase
    has already established (analytics/concentration.py's hhi_label,
    analytics/overlap.py's overlap_label) rather than inventing new ones.
  - Deterministic templating only, never an LLM call (Rule 4) — same
    pattern app/services/market_regime_service.py's own _summary()
    already uses for its plain-English text.
"""
from __future__ import annotations

_SIP_CONSISTENCY_NOTABLE_THRESHOLD_PCT = 60.0
_HOLDING_PERIOD_SHORT_TERM_MAJORITY_THRESHOLD_PCT = 50.0
_NAMES_PREVIEW_COUNT = 3

_SEVERITY_ORDER = {"significant": 0, "notable": 1, "informational": 2}


def _preview_names(items: list[dict], key: str) -> str:
    names = ", ".join(item[key] for item in items[:_NAMES_PREVIEW_COUNT])
    remaining = len(items) - _NAMES_PREVIEW_COUNT
    return f"{names} and {remaining} more" if remaining > 0 else names


def _concentration_insights(structure: dict | None) -> list[dict]:
    if structure is None:
        return []
    insights: list[dict] = []

    scheme_c = structure["scheme_concentration"]
    if scheme_c["hhi_label"] != "diversified":
        severity = "significant" if scheme_c["hhi_label"] == "high_concentration" else "notable"
        insights.append(
            {
                "category": "concentration",
                "severity": severity,
                "message": (
                    f"Your top scheme accounts for {scheme_c['top1_pct']:.1f}% of your currently-held value "
                    f"(HHI {scheme_c['hhi']:.0f}, {scheme_c['hhi_label'].replace('_', ' ')})."
                ),
            }
        )

    # AMC concentration is only a distinct signal once there's more than
    # one AMC to be concentrated across -- with a single AMC it's a
    # restatement of the scheme-concentration insight above.
    amc_c = structure["amc_concentration"]
    if amc_c["count"] is not None and amc_c["count"] > 1 and amc_c["hhi_label"] != "diversified":
        severity = "significant" if amc_c["hhi_label"] == "high_concentration" else "notable"
        insights.append(
            {
                "category": "concentration",
                "severity": severity,
                "message": (
                    f"Across {amc_c['count']} AMCs, your top AMC accounts for {amc_c['top1_pct']:.1f}% of your "
                    f"currently-held value (HHI {amc_c['hhi']:.0f}, {amc_c['hhi_label'].replace('_', ' ')})."
                ),
            }
        )
    return insights


def _overlap_insights(look_through_analysis: dict | None) -> list[dict]:
    if look_through_analysis is None:
        return []
    return [
        {
            "category": "overlap",
            "severity": "notable",
            "message": (
                f"{pair['fund_a_name']} and {pair['fund_b_name']} share {pair['weighted_overlap_pct']:.1f}% of "
                f"their underlying holdings by weight."
            ),
        }
        for pair in look_through_analysis["pairwise_overlap"]
        if pair["overlap_label"] == "high_overlap"
    ]


def _data_completeness_insights(per_scheme: list[dict], unmatched_schemes: list[dict]) -> list[dict]:
    insights: list[dict] = []
    if unmatched_schemes:
        insights.append(
            {
                "category": "data_completeness",
                "severity": "informational",
                "message": (
                    f"{len(unmatched_schemes)} holding(s) in your statement "
                    f"({_preview_names(unmatched_schemes, 'scheme_name')}) aren't in our fund database yet, "
                    "so they're excluded from this analysis."
                ),
            }
        )

    unpriced = [s for s in per_scheme if s["current_value"] is None]
    if unpriced:
        insights.append(
            {
                "category": "data_completeness",
                "severity": "informational",
                "message": (
                    f"{len(unpriced)} matched scheme(s) ({_preview_names(unpriced, 'scheme_name')}) have no price "
                    "history in our database yet, so their current value isn't included in your totals."
                ),
            }
        )
    return insights


def _investment_timing_insights(investment_timing: dict) -> list[dict]:
    if investment_timing["unclassified_purchase_count"] == 0:
        return []
    return [
        {
            "category": "investment_timing",
            "severity": "informational",
            "message": (
                f"{investment_timing['unclassified_purchase_count']} purchase(s) "
                f"(₹{investment_timing['unclassified_invested_amount']:,.0f}) fell outside the date windows we "
                "have market-regime data for."
            ),
        }
    ]


def _sip_consistency_insights(per_scheme: list[dict]) -> list[dict]:
    insights: list[dict] = []
    for scheme in per_scheme:
        sip = scheme["sip_consistency"]
        if sip is None or sip["gap_consistency_pct"] is None:
            continue
        if sip["gap_consistency_pct"] < _SIP_CONSISTENCY_NOTABLE_THRESHOLD_PCT:
            insights.append(
                {
                    "category": "sip_consistency",
                    "severity": "informational",
                    "message": (
                        f"{scheme['scheme_name']}'s SIP installments arrived at irregular intervals (gap "
                        f"consistency {sip['gap_consistency_pct']:.0f}%, averaging {sip['average_gap_days']:.0f} "
                        f"days apart, ranging {sip['min_gap_days']}-{sip['max_gap_days']} days)."
                    ),
                }
            )
    return insights


def _complexity_insights(complexity: dict) -> list[dict]:
    insights: list[dict] = []
    if complexity["folio_count"] > complexity["scheme_count"]:
        insights.append(
            {
                "category": "complexity",
                "severity": "informational",
                "message": (
                    f"At least one scheme is held across more than one folio "
                    f"({complexity['folio_count']} folios for {complexity['scheme_count']} schemes)."
                ),
            }
        )
    if complexity["complexity_label"] in ("Complex", "Highly Complex"):
        insights.append(
            {
                "category": "complexity",
                "severity": "notable",
                "message": (
                    f"Your current holdings span {complexity['scheme_count']} schemes across "
                    f"{complexity['amc_count']} AMCs and {complexity['category_count']} categories."
                ),
            }
        )
    return insights


def _holding_period_insights(holding_period: dict) -> list[dict]:
    short_term = next((b for b in holding_period["open_value_by_bucket"] if b["label"] == "< 1 year"), None)
    if short_term is None or short_term["weight_pct"] <= _HOLDING_PERIOD_SHORT_TERM_MAJORITY_THRESHOLD_PCT:
        return []
    return [
        {
            "category": "holding_period",
            "severity": "informational",
            "message": f"{short_term['weight_pct']:.0f}% of your currently-held value has been held for under a year.",
        }
    ]


def _realized_performance_insights(total_realized_gain: float) -> list[dict]:
    if total_realized_gain >= 0:
        return []
    return [
        {
            "category": "realized_performance",
            "severity": "informational",
            "message": (
                f"Past redemptions/switches in this portfolio have realized a net loss of "
                f"₹{abs(total_realized_gain):,.0f} so far."
            ),
        }
    ]


def _health_check_summary(
    priced_scheme_count: int, total_referenced_scheme_count: int, data_completeness_pct: float | None, severity_counts: dict
) -> str:
    if total_referenced_scheme_count == 0:
        return "No holdings were found in this statement to analyze."

    parts: list[str] = []
    if data_completeness_pct is not None and data_completeness_pct >= 99.9:
        parts.append(f"This analysis covers all {total_referenced_scheme_count} scheme(s) referenced in your statement.")
    elif data_completeness_pct is not None:
        parts.append(
            f"This analysis covers {priced_scheme_count} of {total_referenced_scheme_count} scheme(s) referenced "
            f"in your statement ({data_completeness_pct:.0f}%)."
        )

    total_flagged = sum(severity_counts.values())
    if total_flagged == 0:
        parts.append("No notable patterns were flagged below.")
    else:
        pieces = [f"{severity_counts[level]} {level}" for level in _SEVERITY_ORDER if severity_counts[level] > 0]
        plural = "observation" if total_flagged == 1 else "observations"
        parts.append(f"{total_flagged} {plural} flagged below ({', '.join(pieces)}).")

    return " ".join(parts)


def build_cas_insights(overview: dict) -> dict:
    """`overview`: a FULLY BUILT build_cas_overview() result (every other
    field must already be present — this is the last thing computed).
    Returns {"insights": [...], "health_check": {...}}, sorted
    significant-first so the highest-severity, evidence-based
    observations read first."""
    insights: list[dict] = []
    insights.extend(_concentration_insights(overview["structure"]))
    insights.extend(_overlap_insights(overview["look_through_analysis"]))
    insights.extend(_data_completeness_insights(overview["per_scheme"], overview["unmatched_schemes"]))
    insights.extend(_investment_timing_insights(overview["investment_timing"]))
    insights.extend(_sip_consistency_insights(overview["per_scheme"]))
    insights.extend(_complexity_insights(overview["complexity"]))
    insights.extend(_holding_period_insights(overview["holding_period"]))
    insights.extend(_realized_performance_insights(overview["total_realized_gain"]))
    insights.sort(key=lambda i: _SEVERITY_ORDER[i["severity"]])

    matched_scheme_count = overview["matched_scheme_count"]
    unmatched_count = len(overview["unmatched_schemes"])
    total_referenced_scheme_count = matched_scheme_count + unmatched_count
    priced_scheme_count = sum(1 for s in overview["per_scheme"] if s["current_value"] is not None)
    data_completeness_pct = (
        round(priced_scheme_count / total_referenced_scheme_count * 100, 1)
        if total_referenced_scheme_count > 0
        else None
    )

    severity_counts = {"significant": 0, "notable": 0, "informational": 0}
    for insight in insights:
        severity_counts[insight["severity"]] += 1

    return {
        "insights": insights,
        "health_check": {
            "data_completeness_pct": data_completeness_pct,
            "priced_scheme_count": priced_scheme_count,
            "total_referenced_scheme_count": total_referenced_scheme_count,
            "significant_count": severity_counts["significant"],
            "notable_count": severity_counts["notable"],
            "informational_count": severity_counts["informational"],
            "summary": _health_check_summary(
                priced_scheme_count, total_referenced_scheme_count, data_completeness_pct, severity_counts
            ),
        },
    }
