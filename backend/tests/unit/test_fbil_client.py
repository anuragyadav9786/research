"""Tests for the FBIL T-Bill client's error handling, using a mocked
transport -- deterministic and network-free even though this specific
host is confirmed reachable from this environment (see client.py's
module docstring for the real response shape this was verified against
live, this session)."""
import httpx
import pytest
from datetime import date

from data_pipeline.sources.riskfree.fbil_client import FbilFetchError, fetch_latest_3m_tbill_rate_pct

_SAMPLE_ROWS = [
    {"processRunDate": "2026-10-23 00:00:00", "displayTime": "2026-10-23 17:30:00", "tenorName": "1 Month", "rate": 5.70, "comments": " "},
    {"processRunDate": "2026-10-23 00:00:00", "displayTime": "2026-10-23 17:30:00", "tenorName": "3 Months", "rate": 5.83, "comments": " "},
    {"processRunDate": "2026-10-26 00:00:00", "displayTime": "2026-10-26 17:30:00", "tenorName": "1 Month", "rate": 5.66, "comments": " "},
    {"processRunDate": "2026-10-26 00:00:00", "displayTime": "2026-10-26 17:30:00", "tenorName": "3 Months", "rate": 5.87, "comments": " "},
]


def _client_with_response(handler) -> httpx.Client:
    transport = httpx.MockTransport(handler)
    return httpx.Client(transport=transport)


def _patch_get(monkeypatch, handler):
    monkeypatch.setattr(httpx, "get", lambda url, timeout, follow_redirects: _client_with_response(handler).get(url))


def test_fetch_latest_3m_tbill_rate_picks_the_most_recent_date(monkeypatch):
    def handler(request):
        return httpx.Response(200, json=_SAMPLE_ROWS)

    _patch_get(monkeypatch, handler)
    as_of, rate_pct = fetch_latest_3m_tbill_rate_pct()
    assert as_of == date(2026, 10, 26)
    assert rate_pct == pytest.approx(5.87)


def test_fetch_latest_3m_tbill_rate_raises_on_http_error(monkeypatch):
    def handler(request):
        return httpx.Response(503, text="Service Unavailable")

    _patch_get(monkeypatch, handler)
    with pytest.raises(FbilFetchError, match="503"):
        fetch_latest_3m_tbill_rate_pct()


def test_fetch_latest_3m_tbill_rate_raises_on_timeout(monkeypatch):
    def raise_timeout(url, timeout, follow_redirects):
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(httpx, "get", raise_timeout)
    with pytest.raises(FbilFetchError, match="Timed out"):
        fetch_latest_3m_tbill_rate_pct()


def test_fetch_latest_3m_tbill_rate_raises_when_tenor_missing(monkeypatch):
    def handler(request):
        return httpx.Response(200, json=[{"processRunDate": "2026-10-26 00:00:00", "tenorName": "6 Months", "rate": 6.23}])

    _patch_get(monkeypatch, handler)
    with pytest.raises(FbilFetchError, match="3 Months"):
        fetch_latest_3m_tbill_rate_pct()


def test_fetch_latest_3m_tbill_rate_raises_on_unexpected_shape(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"unexpected": "shape"})

    _patch_get(monkeypatch, handler)
    with pytest.raises(FbilFetchError, match="unexpected"):
        fetch_latest_3m_tbill_rate_pct()


def test_fetch_latest_3m_tbill_rate_raises_on_non_positive_rate(monkeypatch):
    def handler(request):
        return httpx.Response(200, json=[{"processRunDate": "2026-10-26 00:00:00", "tenorName": "3 Months", "rate": 0}])

    _patch_get(monkeypatch, handler)
    with pytest.raises(FbilFetchError, match="non-positive"):
        fetch_latest_3m_tbill_rate_pct()
