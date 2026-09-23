from datetime import date

import pytest

from analytics.cost_basis import apply_fifo


def test_single_lump_sum_no_redemption():
    events = [(date(2024, 1, 1), 100.0, 1000.0)]  # 100 units at NAV 10
    result = apply_fifo(events)
    assert result.remaining_units == pytest.approx(100.0)
    assert result.weighted_average_purchase_nav == pytest.approx(10.0)
    assert result.realized_gain == pytest.approx(0.0)
    assert len(result.open_lots) == 1


def test_sip_then_partial_redemption_consumes_oldest_lot_first():
    events = [
        (date(2024, 1, 1), 100.0, 1000.0),  # lot 1: 100 units @ NAV 10
        (date(2024, 2, 1), 100.0, 1200.0),  # lot 2: 100 units @ NAV 12
        (date(2024, 3, 1), -120.0, -1800.0),  # redeem 120 units @ NAV 15 (proceeds 1800)
    ]
    result = apply_fifo(events)

    # FIFO: the redemption consumes all 100 units of lot 1, then 20 units of lot 2.
    assert len(result.consumptions) == 2
    first, second = result.consumptions
    assert first.purchase_date == date(2024, 1, 1)
    assert first.units == pytest.approx(100.0)
    assert first.cost_per_unit == pytest.approx(10.0)
    assert second.purchase_date == date(2024, 2, 1)
    assert second.units == pytest.approx(20.0)
    assert second.cost_per_unit == pytest.approx(12.0)

    # Remaining: 80 units left of lot 2, at its own cost per unit (12).
    assert result.remaining_units == pytest.approx(80.0)
    assert result.weighted_average_purchase_nav == pytest.approx(12.0)

    # Realized gain = proceeds - cost for the 120 units sold.
    # cost = 100*10 + 20*12 = 1240; proceeds = 120*15 = 1800; gain = 560.
    assert result.realized_cost == pytest.approx(1240.0)
    assert result.realized_proceeds == pytest.approx(1800.0)
    assert result.realized_gain == pytest.approx(560.0)


def test_complete_redemption_leaves_no_open_lots():
    events = [
        (date(2024, 1, 1), 100.0, 1000.0),
        (date(2024, 6, 1), -100.0, -1100.0),
    ]
    result = apply_fifo(events)
    assert result.open_lots == []
    assert result.remaining_units == pytest.approx(0.0)
    assert result.weighted_average_purchase_nav is None
    assert result.realized_gain == pytest.approx(100.0)


def test_holding_period_tracked_per_consumed_lot():
    events = [
        (date(2023, 1, 1), 50.0, 500.0),
        (date(2024, 1, 1), -50.0, 600.0),
    ]
    result = apply_fifo(events)
    assert len(result.consumptions) == 1
    assert result.consumptions[0].holding_period_days == 365


def test_switch_out_and_switch_in_are_independent_lot_streams():
    # A switch is just a negative event on one scheme's stream and a
    # positive event on another's -- apply_fifo is called once per
    # scheme, so this only tests that a switch-out behaves exactly like
    # a redemption for lot-consumption purposes.
    fund_a_events = [(date(2024, 1, 1), 100.0, 1000.0), (date(2024, 6, 1), -100.0, -1200.0)]
    result_a = apply_fifo(fund_a_events)
    assert result_a.remaining_units == pytest.approx(0.0)
    assert result_a.realized_gain == pytest.approx(200.0)

    fund_b_events = [(date(2024, 6, 1), 80.0, 1200.0)]  # switch-in creates a fresh lot
    result_b = apply_fifo(fund_b_events)
    assert result_b.remaining_units == pytest.approx(80.0)
    assert result_b.weighted_average_purchase_nav == pytest.approx(15.0)


def test_redemption_beyond_available_units_is_reported_not_fabricated():
    events = [(date(2024, 1, 1), -10.0, -100.0)]  # a redemption with no prior purchase lot at all
    result = apply_fifo(events)
    assert result.open_lots == []
    assert result.consumptions == []
    assert result.unmatched_redemption_units == pytest.approx(10.0)


def test_empty_events_yields_empty_result():
    result = apply_fifo([])
    assert result.open_lots == []
    assert result.remaining_units == pytest.approx(0.0)
    assert result.weighted_average_purchase_nav is None
