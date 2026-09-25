from datetime import date

import pytest

from app.services.cas_comparison_service import compare_cas_overviews


def _overview(total_invested, total_current_value, total_gain, portfolio_xirr_pct, per_scheme, structure=None):
    return {
        "total_invested": total_invested,
        "total_current_value": total_current_value,
        "total_gain": total_gain,
        "portfolio_xirr_pct": portfolio_xirr_pct,
        "per_scheme": per_scheme,
        "structure": structure,
    }


def _scheme(fund_id, scheme_name, isin, current_value, weight_pct):
    return {
        "fund_id": fund_id,
        "scheme_name": scheme_name,
        "isin": isin,
        "current_value": current_value,
        "weight_pct": weight_pct,
    }


def test_detects_a_new_scheme_and_an_exited_scheme():
    previous = _overview(
        1000.0, 1100.0, 100.0, 8.0,
        per_scheme=[_scheme(1, "Fund A", "ISINA", 1100.0, 100.0)],
    )
    current = _overview(
        1500.0, 1600.0, 100.0, 5.0,
        per_scheme=[_scheme(2, "Fund B", "ISINB", 1600.0, 100.0)],
    )
    diff = compare_cas_overviews(date(2025, 1, 1), previous, date(2025, 7, 1), current)

    assert len(diff["new_schemes"]) == 1
    assert diff["new_schemes"][0]["isin"] == "ISINB"
    assert diff["new_schemes"][0]["current_value"] == pytest.approx(1600.0)

    assert len(diff["exited_schemes"]) == 1
    assert diff["exited_schemes"][0]["isin"] == "ISINA"
    assert diff["exited_schemes"][0]["previous_value"] == pytest.approx(1100.0)

    assert diff["scheme_changes"] == []


def test_a_scheme_held_in_both_snapshots_reports_value_and_weight_change():
    previous = _overview(
        1000.0, 1100.0, 100.0, None,
        per_scheme=[
            _scheme(1, "Fund A", "ISINA", 700.0, 70.0),
            _scheme(2, "Fund B", "ISINB", 300.0, 30.0),
        ],
    )
    current = _overview(
        1000.0, 1300.0, 300.0, None,
        per_scheme=[
            _scheme(1, "Fund A", "ISINA", 900.0, 69.2),
            _scheme(2, "Fund B", "ISINB", 400.0, 30.8),
        ],
    )
    diff = compare_cas_overviews(None, previous, None, current)

    assert diff["new_schemes"] == []
    assert diff["exited_schemes"] == []
    assert len(diff["scheme_changes"]) == 2

    # Sorted by |value_change| descending -> Fund A (200) before Fund B (100).
    fund_a, fund_b = diff["scheme_changes"]
    assert fund_a["isin"] == "ISINA"
    assert fund_a["value_change"] == pytest.approx(200.0)
    assert fund_a["weight_pct_change"] == pytest.approx(69.2 - 70.0, abs=1e-6)
    assert fund_b["isin"] == "ISINB"
    assert fund_b["value_change"] == pytest.approx(100.0)


def test_portfolio_level_deltas_and_span_days():
    previous = _overview(1000.0, 1100.0, 100.0, 8.0, per_scheme=[])
    current = _overview(1500.0, 1650.0, 250.0, 6.5, per_scheme=[])
    diff = compare_cas_overviews(date(2025, 1, 1), previous, date(2025, 4, 11), current)

    assert diff["span_days"] == 100
    assert diff["total_invested_change"] == pytest.approx(500.0)
    assert diff["total_current_value_change"] == pytest.approx(550.0)
    assert diff["total_gain_change"] == pytest.approx(150.0)
    assert diff["portfolio_xirr_pct_previous"] == pytest.approx(8.0)
    assert diff["portfolio_xirr_pct_current"] == pytest.approx(6.5)


def test_span_days_is_none_when_either_as_of_date_is_missing():
    previous = _overview(1000.0, 1000.0, 0.0, None, per_scheme=[])
    current = _overview(1000.0, 1000.0, 0.0, None, per_scheme=[])
    diff = compare_cas_overviews(None, previous, date(2025, 1, 1), current)
    assert diff["span_days"] is None


def test_asset_allocation_drift_compares_weights_and_handles_missing_structure():
    previous_structure = {"asset_allocation": [{"label": "Equity", "value": 700.0, "weight_pct": 70.0}]}
    current_structure = {
        "asset_allocation": [
            {"label": "Equity", "value": 900.0, "weight_pct": 60.0},
            {"label": "Debt", "value": 600.0, "weight_pct": 40.0},
        ]
    }
    previous = _overview(1000.0, 1000.0, 0.0, None, per_scheme=[], structure=previous_structure)
    current = _overview(1500.0, 1500.0, 0.0, None, per_scheme=[], structure=current_structure)
    diff = compare_cas_overviews(None, previous, None, current)

    drift_by_label = {d["label"]: d for d in diff["asset_allocation_drift"]}
    assert drift_by_label["Equity"]["previous_weight_pct"] == pytest.approx(70.0)
    assert drift_by_label["Equity"]["current_weight_pct"] == pytest.approx(60.0)
    assert drift_by_label["Equity"]["weight_pct_change"] == pytest.approx(-10.0)
    # Debt is new in the current snapshot -> previous weight is 0, not fabricated absence.
    assert drift_by_label["Debt"]["previous_weight_pct"] == pytest.approx(0.0)
    assert drift_by_label["Debt"]["weight_pct_change"] == pytest.approx(40.0)


def test_asset_allocation_drift_is_empty_when_a_structure_is_none():
    previous = _overview(0.0, 0.0, 0.0, None, per_scheme=[], structure=None)
    current = _overview(0.0, 0.0, 0.0, None, per_scheme=[], structure=None)
    diff = compare_cas_overviews(None, previous, None, current)
    assert diff["asset_allocation_drift"] == []


def test_a_scheme_still_held_in_both_but_unpriced_in_one_snapshot_is_not_a_scheme_change():
    # current_value None (unpriced, no NAV data) never counts as "held" here.
    previous = _overview(1000.0, 1000.0, 0.0, None, per_scheme=[_scheme(1, "Fund A", "ISINA", 1000.0, 100.0)])
    current = _overview(
        1000.0, 0.0, 0.0, None,
        per_scheme=[{"fund_id": 1, "scheme_name": "Fund A", "isin": "ISINA", "current_value": None, "weight_pct": None}],
    )
    diff = compare_cas_overviews(None, previous, None, current)
    assert diff["scheme_changes"] == []
    assert len(diff["exited_schemes"]) == 1
    assert diff["exited_schemes"][0]["isin"] == "ISINA"
