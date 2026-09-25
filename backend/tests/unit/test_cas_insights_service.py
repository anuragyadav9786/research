from app.services.cas_insights_service import build_cas_insights


def _base_overview(**overrides) -> dict:
    base = {
        "structure": None,
        "look_through_analysis": None,
        "per_scheme": [],
        "unmatched_schemes": [],
        "investment_timing": {"unclassified_purchase_count": 0, "unclassified_invested_amount": 0.0},
        "complexity": {
            "scheme_count": 0,
            "amc_count": 0,
            "category_count": 0,
            "folio_count": 0,
            "complexity_label": "Simple",
        },
        "holding_period": {"open_value_by_bucket": []},
        "total_realized_gain": 0.0,
        "matched_scheme_count": 0,
    }
    base.update(overrides)
    return base


def _concentration_summary(top1_pct, hhi, hhi_label, count=None):
    return {"top1_pct": top1_pct, "hhi": hhi, "hhi_label": hhi_label, "count": count}


def test_no_insights_for_an_empty_simple_portfolio():
    result = build_cas_insights(_base_overview())
    assert result["insights"] == []
    assert result["health_check"]["summary"] == "No holdings were found in this statement to analyze."


def test_high_scheme_concentration_is_significant():
    overview = _base_overview(
        structure={
            "scheme_concentration": _concentration_summary(100.0, 10000.0, "high_concentration"),
            "amc_concentration": _concentration_summary(100.0, 10000.0, "high_concentration", count=1),
        }
    )
    result = build_cas_insights(overview)
    concentration_insights = [i for i in result["insights"] if i["category"] == "concentration"]
    assert len(concentration_insights) == 1
    assert concentration_insights[0]["severity"] == "significant"
    assert "100.0%" in concentration_insights[0]["message"]


def test_moderate_scheme_concentration_is_notable():
    overview = _base_overview(
        structure={
            "scheme_concentration": _concentration_summary(40.0, 2000.0, "moderate_concentration"),
            "amc_concentration": _concentration_summary(40.0, 2000.0, "moderate_concentration", count=1),
        }
    )
    result = build_cas_insights(overview)
    concentration_insights = [i for i in result["insights"] if i["category"] == "concentration"]
    assert len(concentration_insights) == 1
    assert concentration_insights[0]["severity"] == "notable"


def test_diversified_scheme_concentration_produces_no_insight():
    overview = _base_overview(
        structure={
            "scheme_concentration": _concentration_summary(15.0, 800.0, "diversified"),
            "amc_concentration": _concentration_summary(15.0, 800.0, "diversified", count=5),
        }
    )
    result = build_cas_insights(overview)
    assert [i for i in result["insights"] if i["category"] == "concentration"] == []


def test_amc_concentration_only_flagged_with_multiple_amcs():
    # A single-AMC portfolio's AMC concentration is trivially 100% --
    # already covered by the scheme-concentration insight, not a second one.
    overview = _base_overview(
        structure={
            "scheme_concentration": _concentration_summary(100.0, 10000.0, "high_concentration"),
            "amc_concentration": _concentration_summary(100.0, 10000.0, "high_concentration", count=1),
        }
    )
    result = build_cas_insights(overview)
    assert len([i for i in result["insights"] if i["category"] == "concentration"]) == 1


def test_high_overlap_pair_is_flagged_and_low_overlap_is_not():
    overview = _base_overview(
        look_through_analysis={
            "pairwise_overlap": [
                {
                    "fund_a_name": "Fund A",
                    "fund_b_name": "Fund B",
                    "weighted_overlap_pct": 62.5,
                    "overlap_label": "high_overlap",
                },
                {
                    "fund_a_name": "Fund C",
                    "fund_b_name": "Fund D",
                    "weighted_overlap_pct": 5.0,
                    "overlap_label": "low_overlap",
                },
            ]
        }
    )
    result = build_cas_insights(overview)
    overlap_insights = [i for i in result["insights"] if i["category"] == "overlap"]
    assert len(overlap_insights) == 1
    assert "62.5%" in overlap_insights[0]["message"]
    assert overlap_insights[0]["severity"] == "notable"


def test_unmatched_and_unpriced_schemes_are_flagged_informational():
    overview = _base_overview(
        per_scheme=[
            {"scheme_name": "Priced Fund", "current_value": 1000.0, "sip_consistency": None},
            {"scheme_name": "Unpriced Fund", "current_value": None, "sip_consistency": None},
        ],
        unmatched_schemes=[{"scheme_name": "Unknown Fund", "isin": "X"}],
    )
    result = build_cas_insights(overview)
    completeness = [i for i in result["insights"] if i["category"] == "data_completeness"]
    assert len(completeness) == 2
    assert all(i["severity"] == "informational" for i in completeness)
    assert any("Unknown Fund" in i["message"] for i in completeness)
    assert any("Unpriced Fund" in i["message"] for i in completeness)


def test_unclassified_investment_timing_is_flagged():
    overview = _base_overview(
        investment_timing={"unclassified_purchase_count": 2, "unclassified_invested_amount": 1500.0}
    )
    result = build_cas_insights(overview)
    timing_insights = [i for i in result["insights"] if i["category"] == "investment_timing"]
    assert len(timing_insights) == 1
    assert "2 purchase" in timing_insights[0]["message"]
    assert "1,500" in timing_insights[0]["message"]


def test_irregular_sip_is_flagged_but_consistent_sip_is_not():
    overview = _base_overview(
        per_scheme=[
            {
                "scheme_name": "Irregular Fund",
                "current_value": 1000.0,
                "sip_consistency": {
                    "gap_consistency_pct": 40.0,
                    "average_gap_days": 45.0,
                    "min_gap_days": 20,
                    "max_gap_days": 70,
                },
            },
            {
                "scheme_name": "Regular Fund",
                "current_value": 1000.0,
                "sip_consistency": {
                    "gap_consistency_pct": 95.0,
                    "average_gap_days": 30.0,
                    "min_gap_days": 29,
                    "max_gap_days": 31,
                },
            },
            {"scheme_name": "Lumpsum Fund", "current_value": 1000.0, "sip_consistency": None},
        ]
    )
    result = build_cas_insights(overview)
    sip_insights = [i for i in result["insights"] if i["category"] == "sip_consistency"]
    assert len(sip_insights) == 1
    assert "Irregular Fund" in sip_insights[0]["message"]


def test_folio_duplication_and_high_complexity_are_flagged():
    overview = _base_overview(
        complexity={
            "scheme_count": 8,
            "amc_count": 5,
            "category_count": 4,
            "folio_count": 9,
            "complexity_label": "Complex",
        }
    )
    result = build_cas_insights(overview)
    complexity_insights = [i for i in result["insights"] if i["category"] == "complexity"]
    assert len(complexity_insights) == 2
    folio_insight = next(i for i in complexity_insights if "folio" in i["message"])
    assert folio_insight["severity"] == "informational"
    label_insight = next(i for i in complexity_insights if i is not folio_insight)
    assert label_insight["severity"] == "notable"


def test_simple_complexity_with_no_duplicate_folios_is_not_flagged():
    overview = _base_overview(
        complexity={
            "scheme_count": 2,
            "amc_count": 2,
            "category_count": 2,
            "folio_count": 2,
            "complexity_label": "Simple",
        }
    )
    result = build_cas_insights(overview)
    assert [i for i in result["insights"] if i["category"] == "complexity"] == []


def test_short_term_holding_majority_is_flagged():
    overview = _base_overview(
        holding_period={"open_value_by_bucket": [{"label": "< 1 year", "value": 800.0, "weight_pct": 80.0}]}
    )
    result = build_cas_insights(overview)
    holding_insights = [i for i in result["insights"] if i["category"] == "holding_period"]
    assert len(holding_insights) == 1
    assert "80%" in holding_insights[0]["message"]


def test_holding_period_below_threshold_is_not_flagged():
    overview = _base_overview(
        holding_period={"open_value_by_bucket": [{"label": "< 1 year", "value": 300.0, "weight_pct": 30.0}]}
    )
    result = build_cas_insights(overview)
    assert [i for i in result["insights"] if i["category"] == "holding_period"] == []


def test_realized_loss_is_flagged_but_gain_is_not():
    overview = _base_overview(total_realized_gain=-500.0)
    result = build_cas_insights(overview)
    loss_insights = [i for i in result["insights"] if i["category"] == "realized_performance"]
    assert len(loss_insights) == 1
    assert "500" in loss_insights[0]["message"]

    overview_gain = _base_overview(total_realized_gain=500.0)
    result_gain = build_cas_insights(overview_gain)
    assert [i for i in result_gain["insights"] if i["category"] == "realized_performance"] == []


def test_insights_are_sorted_significant_first():
    overview = _base_overview(
        structure={
            "scheme_concentration": _concentration_summary(100.0, 10000.0, "high_concentration"),
            "amc_concentration": _concentration_summary(100.0, 10000.0, "high_concentration", count=1),
        },
        total_realized_gain=-100.0,
        holding_period={"open_value_by_bucket": [{"label": "< 1 year", "value": 900.0, "weight_pct": 90.0}]},
    )
    result = build_cas_insights(overview)
    severities = [i["severity"] for i in result["insights"]]
    assert severities == sorted(severities, key=lambda s: {"significant": 0, "notable": 1, "informational": 2}[s])
    assert severities[0] == "significant"


def test_health_check_data_completeness_and_counts():
    overview = _base_overview(
        per_scheme=[
            {"scheme_name": "Priced Fund", "current_value": 1000.0, "sip_consistency": None},
            {"scheme_name": "Unpriced Fund", "current_value": None, "sip_consistency": None},
        ],
        unmatched_schemes=[{"scheme_name": "Unknown Fund", "isin": "X"}],
        matched_scheme_count=2,
        total_realized_gain=-50.0,
    )
    result = build_cas_insights(overview)
    health = result["health_check"]

    # 1 of 3 referenced schemes (2 matched + 1 unmatched) is actually priced.
    assert health["priced_scheme_count"] == 1
    assert health["total_referenced_scheme_count"] == 3
    assert health["data_completeness_pct"] == round(1 / 3 * 100, 1)
    assert health["informational_count"] == 3  # 2 data-completeness + 1 realized loss
    assert health["significant_count"] == 0
    assert health["notable_count"] == 0
    assert "3 of 3" not in health["summary"]
    assert "1 of 3" in health["summary"]
    assert "3 observations flagged" in health["summary"]


def test_health_check_summary_for_zero_referenced_schemes():
    result = build_cas_insights(_base_overview())
    assert result["health_check"]["data_completeness_pct"] is None
    assert result["health_check"]["summary"] == "No holdings were found in this statement to analyze."
