"""API tests for the Phase 5 fund research endpoints, run against the real
local Postgres database with Phase 2 seed data loaded (same pattern as
tests/api/test_health.py). These are read-only against existing seed
data — no cleanup needed."""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.main import app
from app.models.reference import Scheme, SchemeVariant
from app.models.timeseries import FundMetric
from app.services.fund_analytics_service import MAX_ROLLING_SERIES_POINTS

client = TestClient(app)


@pytest.fixture(scope="module")
def seeded_fund_id() -> int:
    db = SessionLocal()
    try:
        scheme = db.query(Scheme).filter(Scheme.name == "Northbridge Bluechip Equity Fund").first()
        assert scheme is not None, "requires Phase 2 seed data to be loaded"
        return scheme.id
    finally:
        db.close()


def test_list_funds_returns_seeded_schemes():
    response = client.get("/api/funds")
    assert response.status_code == 200
    body = response.json()
    names = [f["scheme_name"] for f in body["items"]]
    assert "Northbridge Bluechip Equity Fund" in names


def test_list_funds_search_filter():
    response = client.get("/api/funds", params={"search": "Midcap"})
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["scheme_name"] == "Meridian Midcap Opportunities Fund"
    assert body["has_more"] is False


def test_list_funds_search_no_match_returns_empty_list():
    response = client.get("/api/funds", params={"search": "NoSuchFundNameXYZ"})
    assert response.status_code == 200
    assert response.json() == {"items": [], "has_more": False}


def test_list_funds_search_is_typo_tolerant():
    # "Meridian" missing its middle 'i' and "Midcap" missing its 'd' — no
    # substring of either word appears verbatim in the real scheme name,
    # so this only passes if fuzzy (word_similarity) matching is active.
    response = client.get("/api/funds", params={"search": "Meridan Micap"})
    assert response.status_code == 200
    body = response.json()
    names = [f["scheme_name"] for f in body["items"]]
    assert "Meridian Midcap Opportunities Fund" in names


def test_list_funds_category_filter_is_substring_match():
    response = client.get("/api/funds", params={"category": "Large Cap"})
    assert response.status_code == 200
    names = [f["scheme_name"] for f in response.json()["items"]]
    assert names == ["Northbridge Bluechip Equity Fund"]


def test_list_funds_category_filter_comma_separated_ors_terms():
    # Comma-separated categories OR together — the persona quick-start
    # cards (e.g. "aggressive": Small Cap + Mid Cap) rely on this to span
    # more than one AMFI category in a single /research link.
    response = client.get("/api/funds", params={"category": "Mid Cap,Flexi Cap"})
    assert response.status_code == 200
    names = {f["scheme_name"] for f in response.json()["items"]}
    assert names == {"Meridian Midcap Opportunities Fund", "Northbridge Flexi Cap Fund"}

    count = client.get("/api/funds/count", params={"category": "Mid Cap,Flexi Cap"})
    assert count.json() == {"count": 2}


def test_list_funds_pagination_has_more_flag():
    first_page = client.get("/api/funds", params={"limit": 2, "offset": 0}).json()
    assert len(first_page["items"]) == 2
    assert first_page["has_more"] is True  # 4 sample funds seeded, more than 2

    last_page = client.get("/api/funds", params={"limit": 2, "offset": 2}).json()
    assert len(last_page["items"]) == 2
    assert last_page["has_more"] is False

    # Pages don't overlap
    first_ids = {f["id"] for f in first_page["items"]}
    last_ids = {f["id"] for f in last_page["items"]}
    assert first_ids.isdisjoint(last_ids)


def test_get_fund_detail_includes_both_variants(seeded_fund_id):
    response = client.get(f"/api/funds/{seeded_fund_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["scheme_name"] == "Northbridge Bluechip Equity Fund"
    plans = {v["plan"] for v in body["variants"]}
    assert plans == {"direct", "regular"}
    for variant in body["variants"]:
        assert variant["latest_nav"] is not None
        assert variant["latest_nav_date"] is not None


def test_get_fund_nav_history_returns_ordered_series(seeded_fund_id):
    response = client.get(f"/api/funds/{seeded_fund_id}/nav-history")
    assert response.status_code == 200
    body = response.json()
    assert body["benchmark_name"] == "Nifty 50 TRI (Sample Series)"
    assert len(body["fund_points"]) > 1000
    assert len(body["benchmark_points"]) > 1000
    dates = [p["date"] for p in body["fund_points"]]
    assert dates == sorted(dates)
    assert all(p["value"] > 0 for p in body["fund_points"])


def test_get_fund_returns_reports_all_windows(seeded_fund_id):
    response = client.get(f"/api/funds/{seeded_fund_id}/returns")
    assert response.status_code == 200
    body = response.json()
    assert set(body["windows"].keys()) == {"1y", "3y", "5y", "7y", "10y"}
    # ~4 years of seed history -> 1y and 3y available, 5y/7y/10y not
    assert body["windows"]["1y"]["available"] is True
    assert body["windows"]["10y"]["available"] is False
    assert body["windows"]["10y"]["reason"] == "insufficient_history"
    assert "disclaimer" in body


def test_get_fund_risk_reports_metrics(seeded_fund_id):
    response = client.get(f"/api/funds/{seeded_fund_id}/risk")
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["observations_used"] > 1000
    assert isinstance(body["volatility_pct"], float)
    assert body["risk_free_rate_pct"] == pytest.approx(7.0)


def test_get_fund_rolling_returns_reports_percentages(seeded_fund_id):
    response = client.get(f"/api/funds/{seeded_fund_id}/rolling-returns", params={"window_years": 1})
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["distribution"]["count"] > 0
    # values should look like percentages (tens), not raw fractions (<1)
    assert abs(body["distribution"]["median"]) < 100
    assert body["benchmark_consistency"]["aligned_windows"] > 0


def test_get_fund_rolling_returns_insufficient_window(seeded_fund_id):
    response = client.get(f"/api/funds/{seeded_fund_id}/rolling-returns", params={"window_years": 10})
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert body["reason"] == "insufficient_history"
    assert body["distribution"]["count"] == 0


def test_get_fund_rolling_returns_series_reports_points(seeded_fund_id):
    response = client.get(
        f"/api/funds/{seeded_fund_id}/rolling-returns-series", params={"window": "3m", "lookback": "1y"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["window"] == "3m"
    assert body["lookback"] == "1y"
    assert body["annualized"] is False  # sub-annual window -> simple return, not CAGR
    assert body["available"] is True
    assert 0 < len(body["points"]) <= MAX_ROLLING_SERIES_POINTS
    for point in body["points"]:
        assert "date" in point and "return_pct" in point


def test_get_fund_rolling_returns_series_1y_window_is_annualized(seeded_fund_id):
    response = client.get(
        f"/api/funds/{seeded_fund_id}/rolling-returns-series", params={"window": "1y", "lookback": "3y"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["annualized"] is True


def test_get_fund_rolling_returns_series_insufficient_history(seeded_fund_id):
    response = client.get(
        f"/api/funds/{seeded_fund_id}/rolling-returns-series", params={"window": "1y", "lookback": "10y"}
    )
    # ~4 years of seed history -> a 1y rolling window still has plenty of
    # points; 10y is only how far back it's trimmed, not a floor on total
    # history, so this should still be available with fewer points than a
    # fund with 10 years of real history would show.
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True


def test_get_fund_rolling_returns_series_invalid_window_returns_422(seeded_fund_id):
    response = client.get(f"/api/funds/{seeded_fund_id}/rolling-returns-series", params={"window": "2m"})
    assert response.status_code == 422


def test_get_fund_drawdown_reports_episode(seeded_fund_id):
    response = client.get(f"/api/funds/{seeded_fund_id}/drawdown")
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["max_drawdown_pct"] < 0
    assert body["peak_date"] is not None
    assert body["trough_date"] is not None


def test_get_fund_risk_serves_precomputed_values_when_cached(seeded_fund_id):
    """Proves /risk actually reads from fund_metrics on a cache hit — by
    seeding an implausible cached value and checking it comes straight
    back unchanged, rather than the real live-computed number."""
    db = SessionLocal()
    try:
        variant = (
            db.query(SchemeVariant)
            .join(Scheme, SchemeVariant.scheme_id == Scheme.id)
            .filter(Scheme.id == seeded_fund_id, SchemeVariant.plan == "direct", SchemeVariant.option == "growth")
            .one()
        )
        analytics_version = get_settings().analytics_version
        today = date.today()
        # Defensive: a nightly precompute run (or another test) touching
        # this same variant/date/version would otherwise collide with the
        # plain insert below.
        db.query(FundMetric).filter(
            FundMetric.scheme_variant_id == variant.id,
            FundMetric.calc_date == today,
            FundMetric.analytics_version == analytics_version,
        ).delete()
        db.commit()
        cached_rows = [
            FundMetric(scheme_variant_id=variant.id, metric_name=name, value=value, calc_date=today, analytics_version=analytics_version)
            for name, value in {
                "volatility_pct": 12.3456,
                "downside_deviation_pct": 5.4321,
                "observations_used": 4242,
                "sharpe_ratio": 1.2345,
            }.items()
        ]
        db.add_all(cached_rows)
        db.commit()

        try:
            response = client.get(f"/api/funds/{seeded_fund_id}/risk")
            assert response.status_code == 200
            body = response.json()
            assert body["available"] is True
            assert body["volatility_pct"] == pytest.approx(12.3456)
            assert body["observations_used"] == 4242
            assert body["sharpe_ratio"] == pytest.approx(1.2345)
            # Not cached for this test -> reconstructed as None, not a live-computed value
            assert body["beta"] is None
        finally:
            db.query(FundMetric).filter(FundMetric.scheme_variant_id == variant.id).delete()
            db.commit()
    finally:
        db.close()


def test_get_fund_intelligence_bundles_everything(seeded_fund_id):
    response = client.get(f"/api/funds/{seeded_fund_id}/intelligence")
    assert response.status_code == 200
    body = response.json()
    assert body["fund"]["id"] == seeded_fund_id
    assert body["variant"]["plan"] == "direct"  # default plan
    assert "windows" in body["returns"]
    assert body["risk"]["available"] is True
    assert body["drawdown"]["available"] is True


def test_unknown_fund_returns_404():
    response = client.get("/api/funds/999999")
    assert response.status_code == 404


def test_unknown_variant_returns_404(seeded_fund_id):
    response = client.get(f"/api/funds/{seeded_fund_id}/returns", params={"option": "idcw"})
    assert response.status_code == 404


def test_invalid_plan_query_param_returns_422(seeded_fund_id):
    response = client.get(f"/api/funds/{seeded_fund_id}/returns", params={"plan": "not-a-real-plan"})
    assert response.status_code == 422
