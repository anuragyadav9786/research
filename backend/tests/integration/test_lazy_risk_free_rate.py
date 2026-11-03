"""End-to-end test of the risk-free-rate cache against the real local
Postgres database. The live FBIL fetch is monkeypatched for determinism
(see fbil_client.py's own module docstring for the real confirmed round
trip) -- everything downstream (the freshness check, the cache write,
and the never-raise fallback) runs for real.
"""
from datetime import date, timedelta

import pytest

import data_pipeline.orchestration.lazy_risk_free_rate as lazy_rate_module
from app.core.database import SessionLocal
from app.core.config import get_settings
from app.models.timeseries import RiskFreeRateSnapshot
from data_pipeline.orchestration.lazy_risk_free_rate import _FRESHNESS_WINDOW_DAYS, get_current_risk_free_rate
from data_pipeline.sources.riskfree.fbil_client import FbilFetchError


@pytest.fixture
def db():
    session = SessionLocal()
    # Other tests' autouse-pinned risk-free-rate fetch (tests/conftest.py)
    # can have already cached a fresh, today-dated snapshot in this real,
    # shared, non-transactional database -- clear it before AND after so
    # each test here starts from a genuinely clean "no snapshot" state.
    session.query(RiskFreeRateSnapshot).delete()
    session.commit()
    yield session
    session.query(RiskFreeRateSnapshot).delete()
    session.commit()
    session.close()


def test_fetches_and_caches_when_no_snapshot_exists(db, monkeypatch):
    monkeypatch.setattr(lazy_rate_module, "fetch_latest_3m_tbill_rate_pct", lambda: (date.today(), 5.87))

    rate = get_current_risk_free_rate(db)

    assert rate == pytest.approx(0.0587)
    snapshot = db.query(RiskFreeRateSnapshot).filter(RiskFreeRateSnapshot.as_of_date == date.today()).one()
    assert float(snapshot.rate_pct) == pytest.approx(5.87)


def test_fresh_cached_snapshot_is_used_without_a_refetch(db, monkeypatch):
    db.add(
        RiskFreeRateSnapshot(
            as_of_date=date.today() - timedelta(days=1),
            rate_pct=6.0,
            source_id=_seed_source(db).id,
        )
    )
    db.commit()

    def _should_not_be_called():
        raise AssertionError("fetch_latest_3m_tbill_rate_pct should not be called when the cache is fresh")

    monkeypatch.setattr(lazy_rate_module, "fetch_latest_3m_tbill_rate_pct", _should_not_be_called)

    rate = get_current_risk_free_rate(db)
    assert rate == pytest.approx(0.06)


def test_stale_snapshot_triggers_a_refetch(db, monkeypatch):
    db.add(
        RiskFreeRateSnapshot(
            as_of_date=date.today() - timedelta(days=_FRESHNESS_WINDOW_DAYS + 1),
            rate_pct=6.0,
            source_id=_seed_source(db).id,
        )
    )
    db.commit()

    monkeypatch.setattr(lazy_rate_module, "fetch_latest_3m_tbill_rate_pct", lambda: (date.today(), 5.5))

    rate = get_current_risk_free_rate(db)
    assert rate == pytest.approx(0.055)


def test_failed_refetch_falls_back_to_the_stale_cached_value(db, monkeypatch):
    db.add(
        RiskFreeRateSnapshot(
            as_of_date=date.today() - timedelta(days=_FRESHNESS_WINDOW_DAYS + 1),
            rate_pct=6.0,
            source_id=_seed_source(db).id,
        )
    )
    db.commit()

    def _raise():
        raise FbilFetchError("simulated network failure")

    monkeypatch.setattr(lazy_rate_module, "fetch_latest_3m_tbill_rate_pct", _raise)

    rate = get_current_risk_free_rate(db)
    assert rate == pytest.approx(0.06)  # the stale cached value, never a fabricated/default one when a real value exists


def test_failed_refetch_with_no_cache_at_all_falls_back_to_settings_default(db, monkeypatch):
    def _raise():
        raise FbilFetchError("simulated network failure")

    monkeypatch.setattr(lazy_rate_module, "fetch_latest_3m_tbill_rate_pct", _raise)

    rate = get_current_risk_free_rate(db)
    assert rate == pytest.approx(get_settings().risk_free_rate)


def _seed_source(db):
    from data_pipeline.storage.database_writer import get_or_create_data_source

    source = get_or_create_data_source(
        db, name=lazy_rate_module.DATA_SOURCE_NAME, url=lazy_rate_module.DATA_SOURCE_URL, source_type="rbi"
    )
    db.commit()
    return source
