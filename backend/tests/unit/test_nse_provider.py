"""Tests for the NSE benchmark provider's HTTP client, using a mocked
transport — no real network access (this sandbox has no outbound internet
access at all; see nse.py's module docstring for why the live
request/response shape is unverified rather than confirmed, unlike
mfapi.in's client)."""
from datetime import date

import httpx
import pytest

from data_pipeline.sources.benchmarks.base import BenchmarkProviderError
from data_pipeline.sources.benchmarks.nse import NSEProvider


def _patch_post(monkeypatch, handler):
    calls = []

    def fake_post(url, json, timeout, headers):
        calls.append(json)
        transport = httpx.MockTransport(handler)
        return httpx.Client(transport=transport).post(url, json=json)

    monkeypatch.setattr(httpx, "post", fake_post)
    return calls


def test_fetch_range_returns_points_on_success(monkeypatch):
    def handler(request):
        return httpx.Response(
            200,
            json={
                "d": (
                    '[{"HistoricalDate": "01-Jan-2025", "EOD_CLOSE_INDEX_VAL": "28000.10"}, '
                    '{"HistoricalDate": "02-Jan-2025", "EOD_CLOSE_INDEX_VAL": "28100.50"}]'
                )
            },
        )

    _patch_post(monkeypatch, handler)
    provider = NSEProvider()
    points = provider.fetch_range("NIFTY 100", date(2025, 1, 1), date(2025, 1, 2))

    assert len(points) == 2
    assert points[0].price_date == date(2025, 1, 1)
    assert points[0].value == 28000.10
    assert points[1].value == 28100.50


def test_fetch_range_sends_expected_payload(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"d": '[{"HistoricalDate": "01-Jan-2025", "EOD_CLOSE_INDEX_VAL": "1"}]'})

    calls = _patch_post(monkeypatch, handler)
    NSEProvider().fetch_range("NIFTY 50 TRI", date(2025, 1, 1), date(2025, 1, 31))

    assert calls[0] == {"name": "NIFTY 50 TRI", "startDate": "01-Jan-2025", "endDate": "31-Jan-2025"}


def test_fetch_range_raises_on_http_error(monkeypatch):
    def handler(request):
        return httpx.Response(404, text="not found")

    _patch_post(monkeypatch, handler)
    with pytest.raises(BenchmarkProviderError, match="404"):
        NSEProvider().fetch_range("UNKNOWN INDEX", date(2025, 1, 1), date(2025, 1, 2))


def test_fetch_range_raises_on_non_json_response(monkeypatch):
    def handler(request):
        return httpx.Response(200, text="<html>not json</html>")

    _patch_post(monkeypatch, handler)
    with pytest.raises(BenchmarkProviderError, match="non-JSON"):
        NSEProvider().fetch_range("NIFTY 100", date(2025, 1, 1), date(2025, 1, 2))


def test_fetch_range_raises_on_unexpected_shape(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"unexpected": "shape"})

    _patch_post(monkeypatch, handler)
    with pytest.raises(BenchmarkProviderError, match="unexpected"):
        NSEProvider().fetch_range("NIFTY 100", date(2025, 1, 1), date(2025, 1, 2))


def test_fetch_range_raises_on_empty_rows(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"d": "[]"})

    _patch_post(monkeypatch, handler)
    with pytest.raises(BenchmarkProviderError, match="no historical data"):
        NSEProvider().fetch_range("NIFTY 100", date(2025, 1, 1), date(2025, 1, 2))


def test_fetch_range_skips_malformed_rows_but_keeps_valid_ones(monkeypatch):
    def handler(request):
        return httpx.Response(
            200,
            json={
                "d": (
                    '[{"HistoricalDate": "not-a-date", "EOD_CLOSE_INDEX_VAL": "100"}, '
                    '{"HistoricalDate": "01-Jan-2025", "EOD_CLOSE_INDEX_VAL": "not-a-number"}, '
                    '{"HistoricalDate": "02-Jan-2025", "EOD_CLOSE_INDEX_VAL": "-5"}, '
                    '{"HistoricalDate": "03-Jan-2025", "EOD_CLOSE_INDEX_VAL": "28000.10"}]'
                )
            },
        )

    _patch_post(monkeypatch, handler)
    points = NSEProvider().fetch_range("NIFTY 100", date(2025, 1, 1), date(2025, 1, 3))

    assert len(points) == 1
    assert points[0].price_date == date(2025, 1, 3)
    assert points[0].value == 28000.10


def test_fetch_range_retries_on_rate_limit_then_succeeds(monkeypatch):
    attempts = {"n": 0}

    def handler(request):
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(429, text="rate limited")
        return httpx.Response(200, json={"d": '[{"HistoricalDate": "01-Jan-2025", "EOD_CLOSE_INDEX_VAL": "1"}]'})

    _patch_post(monkeypatch, handler)
    points = NSEProvider().fetch_range("NIFTY 100", date(2025, 1, 1), date(2025, 1, 1))

    assert attempts["n"] == 2
    assert len(points) == 1
