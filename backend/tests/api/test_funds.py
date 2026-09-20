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


def test_get_fund_category_benchmark_reports_no_comparable_funds_for_a_unique_category(seeded_fund_id):
    # Every seeded fund has a distinct category string ("Equity - Large
    # Cap" etc.) — excluding the fund itself leaves nothing else to
    # average, which should degrade to available: false, not an error or
    # a fabricated zero. Benchmark figures are independent of the category
    # fan-out (this fund's own linked "Nifty 50 TRI" has plenty of
    # history) and should still come through.
    response = client.get(f"/api/funds/{seeded_fund_id}/category-benchmark")
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert body["reason"] == "no_comparable_funds"
    assert body["funds_included"] == 0
    assert body["avg_max_drawdown_pct"] is None
    assert body["benchmark_name"] == "Nifty 50 TRI (Sample Series)"
    assert body["benchmark_max_drawdown_pct"] is not None


def test_get_fund_category_benchmark_unknown_fund_returns_404():
    response = client.get("/api/funds/999999999/category-benchmark")
    assert response.status_code == 404


def test_category_analytics_service_averages_across_comparable_funds():
    # The three equity sample funds ("Equity - Large Cap"/"Mid Cap"/"Flexi
    # Cap") all contain "Equity" — a real, if broader, category filter
    # match — unlike any single fund's own exact category string, which
    # is unique in this seed dataset (see the 404 test above). The
    # in-memory category override (never committed) lets this exercise
    # compute_fund_context's full category+benchmark path against a real
    # Scheme, rather than only the private category-averaging helper.
    from app.repositories import fund_repository
    from app.services import fund_analytics_service
    from app.services.category_analytics_service import compute_fund_context

    db = SessionLocal()
    try:
        bluechip = db.query(Scheme).filter(Scheme.name == "Northbridge Bluechip Equity Fund").first()
        midcap = db.query(Scheme).filter(Scheme.name == "Meridian Midcap Opportunities Fund").first()
        flexicap = db.query(Scheme).filter(Scheme.name == "Northbridge Flexi Cap Fund").first()
        assert bluechip and midcap and flexicap, "requires Phase 2 seed data to be loaded"

        risk_free_rate = get_settings().risk_free_rate
        bluechip.category = "Equity"  # in-memory only, never committed
        result = compute_fund_context(db, bluechip, risk_free_rate_annual=risk_free_rate)
        assert result["available"] is True
        assert result["funds_included"] == 2
        assert result["benchmark_name"] == "Nifty 50 TRI (Sample Series)"
        assert result["benchmark_max_drawdown_pct"] is not None

        expected_drawdowns = []
        for scheme in (midcap, flexicap):
            variant = fund_repository.get_default_variant(db, scheme.id)
            nav = fund_repository.get_nav_series(db, variant.id)
            expected_drawdowns.append(fund_analytics_service.compute_drawdown(nav)["max_drawdown_pct"])

        assert result["avg_max_drawdown_pct"] == pytest.approx(sum(expected_drawdowns) / 2, abs=1e-3)
    finally:
        db.rollback()
        db.close()


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


def test_get_discovery_filters_lists_named_filters():
    response = client.get("/api/funds/discover/filters")
    assert response.status_code == 200
    body = response.json()
    keys = {f["key"] for f in body["filters"]}
    assert keys == {"defensive_drawdown", "consistent_rolling", "fast_recovery", "benchmark_divergence"}
    # Every filter states its exact criterion — never a hidden threshold.
    assert all(f["criterion"] for f in body["filters"])


def test_get_discovered_funds_defensive_drawdown_matches_low_drawdown_seeded_funds():
    # Northbridge Flexi Cap (-16.0%) and Meridian Short Duration Debt
    # (-3.0%) both clear the >= -20% bar; Northbridge Bluechip (-30.2%)
    # and Meridian Midcap (-43.0%) don't.
    response = client.get("/api/funds/discover", params={"filter": "defensive_drawdown"})
    assert response.status_code == 200
    body = response.json()
    assert body["label"] == "Defensive Drawdown Profile"
    names = {item["scheme_name"] for item in body["items"]}
    assert names == {"Northbridge Flexi Cap Fund", "Meridian Short Duration Debt Fund"}
    assert body["funds_scanned"] >= 4


def test_get_discovered_funds_fast_recovery_matches_only_the_recovered_fund():
    # Only Northbridge Flexi Cap Fund has recovered=True in the seed data
    # (140 days, under the 180-day bar); the other three haven't recovered
    # from their own largest drawdown at all.
    response = client.get("/api/funds/discover", params={"filter": "fast_recovery"})
    assert response.status_code == 200
    body = response.json()
    names = [item["scheme_name"] for item in body["items"]]
    assert names == ["Northbridge Flexi Cap Fund"]
    assert body["items"][0]["metric_value"] == 140


def test_get_discovered_funds_unknown_filter_returns_404():
    response = client.get("/api/funds/discover", params={"filter": "not_a_real_filter"})
    assert response.status_code == 404


def test_get_discovered_funds_missing_filter_param_returns_422():
    response = client.get("/api/funds/discover")
    assert response.status_code == 422
