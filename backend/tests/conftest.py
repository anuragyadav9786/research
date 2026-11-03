"""Shared fixtures for the backend test suite.

Autouse-disables the Phase 15 lazy NAV backfill (mfapi.in) for every test
by default. Most tests exercise fund endpoints against Phase 2's fictional
sample scheme codes ("SMP..."), which aren't real AMFI codes — without
this, every API test that resolves a variant would attempt (and fail) a
real outbound HTTP call to api.mfapi.in on every run, since
nav_history_backfilled_at starts unset for all seed data. Tests that
specifically exercise the lazy backfill itself
(tests/integration/test_lazy_nav_backfill.py, tests/unit/test_mfapi_*)
monkeypatch the mfapi client/orchestration function directly instead and
don't rely on this fixture.

Also autouse-pins the risk-free rate (FBIL, real and reachable from this
environment — see data_pipeline/orchestration/lazy_risk_free_rate.py) to
the historical placeholder value (7.0%) for every test by default, so the
ordinary suite never depends on a real outbound HTTP call or on whatever
FBIL happens to be quoting today. Patched at `fetch_latest_3m_tbill_rate_pct`
-- the one name every call site's `get_current_risk_free_rate(db)` actually
resolves through, however it was imported — so this single patch point
covers every caller. tests/integration/test_lazy_risk_free_rate.py and
tests/unit/test_fbil_client.py exercise the real fetch-and-cache logic
directly and re-monkeypatch this same name per test, overriding this
default for their own duration.
"""
from __future__ import annotations

import pytest

import app.api.funds as funds_module
import data_pipeline.orchestration.lazy_risk_free_rate as lazy_risk_free_rate_module
from data_pipeline.orchestration.lazy_nav_backfill import LazyBackfillOutcome


@pytest.fixture(autouse=True)
def _disable_lazy_nav_backfill(monkeypatch):
    monkeypatch.setattr(
        funds_module, "ensure_nav_history", lambda db, variant: LazyBackfillOutcome(attempted=False)
    )


@pytest.fixture(autouse=True)
def _pin_risk_free_rate(monkeypatch):
    import datetime

    monkeypatch.setattr(
        lazy_risk_free_rate_module, "fetch_latest_3m_tbill_rate_pct", lambda: (datetime.date.today(), 7.0)
    )
