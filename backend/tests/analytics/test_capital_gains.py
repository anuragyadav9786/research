from datetime import date

import pytest

from analytics.capital_gains import (
    TAX_ORIENTATION_DEBT,
    TAX_ORIENTATION_EQUITY,
    TAX_ORIENTATION_INDETERMINATE,
    classify_lot_gain,
    classify_tax_orientation,
    summarize_capital_gains,
)
from analytics.cost_basis import Lot


def test_equity_scheme_category_classifies_as_equity_oriented():
    assert classify_tax_orientation("Equity Scheme - Large Cap Fund") == TAX_ORIENTATION_EQUITY
    assert classify_tax_orientation("Equity - Flexi Cap") == TAX_ORIENTATION_EQUITY


def test_debt_scheme_category_classifies_as_debt_oriented():
    assert classify_tax_orientation("Debt Scheme - Liquid Fund") == TAX_ORIENTATION_DEBT


def test_aggressive_hybrid_and_arbitrage_classify_as_equity_oriented():
    assert classify_tax_orientation("Hybrid Scheme - Aggressive Hybrid Fund") == TAX_ORIENTATION_EQUITY
    assert classify_tax_orientation("Hybrid Scheme - Arbitrage Fund") == TAX_ORIENTATION_EQUITY
    assert classify_tax_orientation("Hybrid Scheme - Equity Savings") == TAX_ORIENTATION_EQUITY


def test_conservative_and_balanced_hybrid_classify_as_debt_oriented():
    assert classify_tax_orientation("Hybrid Scheme - Conservative Hybrid Fund") == TAX_ORIENTATION_DEBT
    assert classify_tax_orientation("Hybrid Scheme - Balanced Hybrid Fund") == TAX_ORIENTATION_DEBT


def test_dynamic_asset_allocation_and_gold_are_indeterminate_not_guessed():
    assert classify_tax_orientation("Hybrid Scheme - Dynamic Asset Allocation Fund") == TAX_ORIENTATION_INDETERMINATE
    assert classify_tax_orientation("Other Scheme - Gold ETF") == TAX_ORIENTATION_INDETERMINATE
    assert classify_tax_orientation("Some Unrecognized Wording") == TAX_ORIENTATION_INDETERMINATE


def test_equity_lot_held_over_12_months_is_ltcg_at_12_5_pct():
    lot = Lot(purchase_date=date(2024, 1, 1), units=100.0, cost_per_unit=10.0)  # cost = 1000
    result = classify_lot_gain(lot, as_of=date(2025, 6, 1), current_nav=15.0, tax_orientation=TAX_ORIENTATION_EQUITY)

    assert result.classification == "LTCG"
    assert result.applicable_rate_pct == pytest.approx(12.5)
    assert result.unrealized_gain == pytest.approx(500.0)  # 100*15 - 1000
    assert result.tax_if_realized_today == pytest.approx(500.0 * 0.125)


def test_equity_lot_held_12_months_or_less_is_stcg_at_20_pct():
    lot = Lot(purchase_date=date(2025, 1, 1), units=100.0, cost_per_unit=10.0)
    result = classify_lot_gain(lot, as_of=date(2025, 6, 1), current_nav=12.0, tax_orientation=TAX_ORIENTATION_EQUITY)

    assert result.classification == "STCG"
    assert result.applicable_rate_pct == pytest.approx(20.0)
    assert result.tax_if_realized_today == pytest.approx(200.0 * 0.20)


def test_debt_lot_acquired_before_apr_2023_and_held_over_24_months_is_ltcg():
    lot = Lot(purchase_date=date(2022, 1, 1), units=100.0, cost_per_unit=10.0)
    result = classify_lot_gain(lot, as_of=date(2025, 1, 1), current_nav=13.0, tax_orientation=TAX_ORIENTATION_DEBT)

    assert result.classification == "LTCG"
    assert result.applicable_rate_pct == pytest.approx(12.5)


def test_debt_lot_acquired_on_or_after_apr_2023_is_slab_rate_dependent_never_fabricated():
    lot = Lot(purchase_date=date(2023, 6, 1), units=100.0, cost_per_unit=10.0)
    result = classify_lot_gain(lot, as_of=date(2026, 1, 1), current_nav=13.0, tax_orientation=TAX_ORIENTATION_DEBT)

    assert result.classification is None
    assert result.applicable_rate_pct is None
    assert result.tax_if_realized_today is None
    assert "slab" in result.tax_basis.lower()


def test_indeterminate_orientation_never_assigns_a_rate():
    lot = Lot(purchase_date=date(2022, 1, 1), units=100.0, cost_per_unit=10.0)
    result = classify_lot_gain(lot, as_of=date(2025, 1, 1), current_nav=13.0, tax_orientation=TAX_ORIENTATION_INDETERMINATE)

    assert result.classification is None
    assert result.applicable_rate_pct is None
    assert result.tax_if_realized_today is None


def test_a_loss_is_never_taxed_today():
    lot = Lot(purchase_date=date(2024, 1, 1), units=100.0, cost_per_unit=10.0)
    result = classify_lot_gain(lot, as_of=date(2025, 6, 1), current_nav=8.0, tax_orientation=TAX_ORIENTATION_EQUITY)

    assert result.unrealized_gain == pytest.approx(-200.0)
    assert result.tax_if_realized_today == pytest.approx(0.0)


def test_summarize_capital_gains_buckets_and_totals_only_known_amounts():
    equity_ltcg_lot = Lot(purchase_date=date(2024, 1, 1), units=100.0, cost_per_unit=10.0)
    debt_slab_lot = Lot(purchase_date=date(2024, 6, 1), units=100.0, cost_per_unit=10.0)

    classifications = [
        classify_lot_gain(equity_ltcg_lot, date(2025, 6, 1), current_nav=15.0, tax_orientation=TAX_ORIENTATION_EQUITY),
        classify_lot_gain(debt_slab_lot, date(2025, 6, 1), current_nav=11.0, tax_orientation=TAX_ORIENTATION_DEBT),
    ]
    summary = summarize_capital_gains(classifications)

    assert summary["by_bucket"]["LTCG"]["lot_count"] == 1
    assert summary["by_bucket"]["slab_rate_dependent"]["lot_count"] == 1
    # Total only reflects the LTCG lot's known tax -- the slab-dependent lot contributes nothing fabricated.
    assert summary["total_tax_if_realized_today"] == pytest.approx(500.0 * 0.125)
    assert summary["equity_ltcg_exemption_note"] is not None
