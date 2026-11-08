import pytest

from app.repositories.portfolio_repository import HoldingRow
from app.services.portfolio_intelligence_service import compute_portfolio_dna


def _holding(
    security_id: int,
    security_name: str,
    weight_pct: float,
    sector_name: str | None = None,
    market_cap_category: str | None = None,
    instrument_type: str | None = None,
    credit_rating: str | None = None,
    ytm_pct: float | None = None,
) -> HoldingRow:
    return HoldingRow(
        security_id=security_id,
        security_name=security_name,
        sector_name=sector_name,
        market_cap_category=market_cap_category,
        instrument_type=instrument_type,
        credit_rating=credit_rating,
        ytm_pct=ytm_pct,
        weight_pct=weight_pct,
    )


def test_no_holdings_returns_unavailable_with_new_fields_empty():
    result = compute_portfolio_dna([])
    assert result["available"] is False
    assert result["instrument_type_allocation"] == []
    assert result["credit_quality_allocation"] == []
    assert result["credit_quality_coverage_pct"] is None
    assert result["average_ytm_pct"] is None


def test_all_equity_portfolio_has_no_credit_quality_or_ytm():
    holdings = [
        _holding(1, "Stock A", 60.0, sector_name="Banks", market_cap_category="large_cap", instrument_type="equity"),
        _holding(2, "Stock B", 40.0, sector_name="IT", market_cap_category="large_cap", instrument_type="equity"),
    ]
    result = compute_portfolio_dna(holdings)
    assert result["instrument_type_allocation"] == [{"label": "equity", "weight_pct": 100.0}]
    assert result["credit_quality_allocation"] == []
    assert result["credit_quality_coverage_pct"] is None
    assert result["average_ytm_pct"] is None
    # Equity holdings pass security_id/instrument_type through to top_holdings unchanged.
    assert result["top_holdings"][0]["security_id"] == 1
    assert result["top_holdings"][0]["instrument_type"] == "equity"
    assert result["top_holdings"][0]["credit_rating"] is None


def test_debt_portfolio_instrument_type_and_credit_quality_cover_full_weight():
    holdings = [
        _holding(1, "364 Days Tbill", 50.0, instrument_type="money_market", credit_rating="SOVEREIGN", ytm_pct=6.8),
        _holding(2, "Some NCD", 50.0, instrument_type="debt", credit_rating="CRISIL AAA", ytm_pct=7.2),
    ]
    result = compute_portfolio_dna(holdings)

    assert {s["label"] for s in result["instrument_type_allocation"]} == {"money_market", "debt"}
    assert result["sector_allocation"] == [{"label": "unclassified", "weight_pct": 100.0}]

    credit_quality = {s["label"]: s["weight_pct"] for s in result["credit_quality_allocation"]}
    assert credit_quality == {"SOVEREIGN": 50.0, "CRISIL AAA": 50.0}
    assert result["credit_quality_coverage_pct"] == pytest.approx(100.0)

    # Weighted average: (6.8*50 + 7.2*50) / 100 = 7.0
    assert result["average_ytm_pct"] == pytest.approx(7.0)


def test_mixed_portfolio_credit_quality_coverage_excludes_unrated_equity():
    holdings = [
        _holding(1, "Equity Stock", 70.0, instrument_type="equity"),
        _holding(2, "G-Sec", 30.0, instrument_type="government_security", credit_rating="SOVEREIGN", ytm_pct=7.0),
    ]
    result = compute_portfolio_dna(holdings)

    assert result["credit_quality_allocation"] == [{"label": "SOVEREIGN", "weight_pct": 30.0}]
    # Coverage is only over the rated 30%, not the full 100% disclosed weight.
    assert result["credit_quality_coverage_pct"] == pytest.approx(30.0)
    # Average YTM is also only over holdings that actually carry one — the
    # unrated equity row doesn't dilute it.
    assert result["average_ytm_pct"] == pytest.approx(7.0)


def test_no_holding_has_ytm_returns_none_not_zero():
    holdings = [_holding(1, "Stock A", 100.0, instrument_type="equity")]
    result = compute_portfolio_dna(holdings)
    assert result["average_ytm_pct"] is None
