from datetime import date

import pytest

from analytics.xirr import xirr


def test_xirr_simple_one_year_round_trip():
    # Invest 100000, get back 110000 exactly 365 days later -> exactly 10%.
    # 2025 is not a leap year, so 2025-01-01 -> 2026-01-01 is exactly 365 days.
    cash_flows = [(date(2025, 1, 1), -100_000.0), (date(2026, 1, 1), 110_000.0)]
    assert xirr(cash_flows) == pytest.approx(0.10, abs=1e-4)


def test_xirr_known_textbook_case():
    # Classic XIRR example: -10000 on 2020-01-01, +2750 on 2020-03-01,
    # +4250 on 2020-10-30, +3250 on 2021-02-15, +2750 on 2021-04-01.
    # Excel's XIRR for this sequence is ~0.373362.
    cash_flows = [
        (date(2020, 1, 1), -10_000.0),
        (date(2020, 3, 1), 2_750.0),
        (date(2020, 10, 30), 4_250.0),
        (date(2021, 2, 15), 3_250.0),
        (date(2021, 4, 1), 2_750.0),
    ]
    assert xirr(cash_flows) == pytest.approx(0.373362, abs=1e-4)


def test_xirr_sip_like_series_is_positive_for_a_growing_investment():
    # Twelve monthly investments of 1000, then a redemption of 13500 ->
    # a real, unremarkable positive return; just checking sign + rough
    # magnitude rather than a precise closed-form value.
    cash_flows = [(date(2024, m, 1), -1000.0) for m in range(1, 13)]
    cash_flows.append((date(2025, 1, 1), 13_500.0))
    result = xirr(cash_flows)
    assert result is not None
    assert 0 < result < 1.0


def test_xirr_none_for_single_cash_flow():
    assert xirr([(date(2024, 1, 1), -1000.0)]) is None


def test_xirr_none_for_all_outflows():
    cash_flows = [(date(2024, 1, 1), -1000.0), (date(2024, 6, 1), -500.0)]
    assert xirr(cash_flows) is None


def test_xirr_none_for_all_inflows():
    cash_flows = [(date(2024, 1, 1), 1000.0), (date(2024, 6, 1), 500.0)]
    assert xirr(cash_flows) is None


def test_xirr_handles_a_loss():
    # Invest 100000, get back only 80000 exactly 365 days later -> -20%.
    cash_flows = [(date(2025, 1, 1), -100_000.0), (date(2026, 1, 1), 80_000.0)]
    result = xirr(cash_flows)
    assert result is not None
    assert result == pytest.approx(-0.20, abs=1e-4)
