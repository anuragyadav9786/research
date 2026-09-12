"""Unit tests for the pure row-building logic in precompute_metrics.py —
deciding which metric rows to write for one variant given already-computed
returns/risk/drawdown dicts (the same shapes fund_analytics_service.py's
compute_returns/compute_risk/compute_drawdown produce)."""
from datetime import date

from data_pipeline.orchestration.precompute_metrics import _rows_for_variant

CALC_DATE = date(2026, 9, 12)
VERSION = "v-test"


def _returns(**window_overrides):
    windows = {
        w: {"available": False, "cagr_pct": None, "start_date": None, "end_date": None, "reason": "insufficient_history"}
        for w in ("1y", "3y", "5y", "7y", "10y")
    }
    windows.update(window_overrides)
    return {"as_of_date": CALC_DATE.isoformat(), "windows": windows}


def _available_window(cagr_pct: float) -> dict:
    return {"available": True, "cagr_pct": cagr_pct, "start_date": "2025-01-01", "end_date": "2026-01-01", "reason": None}


def _risk(available: bool = True, **overrides) -> dict:
    base = {
        "available": available,
        "reason": None if available else "insufficient_history",
        "observations_used": 500,
        "risk_free_rate_pct": 7.0,
        "volatility_pct": 12.5,
        "downside_deviation_pct": 8.1,
        "sharpe_ratio": 0.9,
        "sortino_ratio": 1.1,
        "upside_capture_pct": 105.0,
        "downside_capture_pct": 90.0,
        "beta": 0.95,
        "jensen_alpha_pct": 0.5,
    }
    base.update(overrides)
    return base


def _drawdown(available: bool = True, max_drawdown_pct: float = -18.5) -> dict:
    if not available:
        return {"available": False, "reason": "insufficient_history", "max_drawdown_pct": None}
    return {"available": True, "reason": None, "max_drawdown_pct": max_drawdown_pct}


def test_writes_a_row_per_available_return_window():
    returns = _returns(**{"1y": _available_window(12.3), "3y": _available_window(9.8)})
    rows = _rows_for_variant(1, returns, _risk(available=False), _drawdown(available=False), CALC_DATE, VERSION)
    names_values = {r["metric_name"]: r["value"] for r in rows}
    assert names_values["cagr_1y"] == 12.3
    assert names_values["cagr_3y"] == 9.8
    assert "cagr_5y" not in names_values  # unavailable window -> no row


def test_writes_all_risk_fields_when_fully_available():
    rows = _rows_for_variant(1, _returns(), _risk(), _drawdown(available=False), CALC_DATE, VERSION)
    names = {r["metric_name"] for r in rows}
    assert names == {
        "volatility_pct", "downside_deviation_pct", "observations_used",
        "sharpe_ratio", "sortino_ratio", "upside_capture_pct", "downside_capture_pct", "beta", "jensen_alpha_pct",
    }


def test_skips_none_optional_risk_fields_no_benchmark_case():
    # Mirrors a fund with no benchmark: capture ratios/beta/jensen_alpha
    # stay None even though available=True (see compute_risk).
    risk = _risk(sharpe_ratio=0.9, sortino_ratio=1.1, upside_capture_pct=None, downside_capture_pct=None, beta=None, jensen_alpha_pct=None)
    rows = _rows_for_variant(1, _returns(), risk, _drawdown(available=False), CALC_DATE, VERSION)
    names = {r["metric_name"] for r in rows}
    assert "upside_capture_pct" not in names
    assert "beta" not in names
    assert "sharpe_ratio" in names  # still present, just not None


def test_writes_nothing_for_risk_when_unavailable():
    rows = _rows_for_variant(1, _returns(), _risk(available=False), _drawdown(available=False), CALC_DATE, VERSION)
    assert rows == []


def test_writes_max_drawdown_only_when_available():
    rows = _rows_for_variant(1, _returns(), _risk(available=False), _drawdown(max_drawdown_pct=-22.1), CALC_DATE, VERSION)
    assert rows == [
        {"scheme_variant_id": 1, "metric_name": "max_drawdown_pct", "value": -22.1, "calc_date": CALC_DATE, "analytics_version": VERSION}
    ]


def test_rows_carry_correct_identity_fields():
    rows = _rows_for_variant(42, _returns(**{"1y": _available_window(5.0)}), _risk(available=False), _drawdown(available=False), CALC_DATE, VERSION)
    assert rows[0]["scheme_variant_id"] == 42
    assert rows[0]["calc_date"] == CALC_DATE
    assert rows[0]["analytics_version"] == VERSION
