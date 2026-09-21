"""Tests for the NSE benchmark provider's HTTP client, using a mocked
transport — no real network access (this sandbox has no outbound internet
access at all). Unlike the module's earlier version, the response shape
used here is a REAL captured sample from
GET https://www.nseindia.com/api/historicalOR/indicesHistory — see
nse.py's module docstring — not a guess; only the session-handshake/
request mechanics remain a best-effort simulation."""
from datetime import date

import httpx
import pytest

from data_pipeline.sources.benchmarks.base import BenchmarkProviderError
from data_pipeline.sources.benchmarks.nse import NSEProvider

REAL_SAMPLE_RESPONSE = {
    "data": {
        "indexCloseOnlineRecords": [
            {
                "EOD_OPEN_INDEX_VAL": 10881.7,
                "EOD_HIGH_INDEX_VAL": 10923.6,
                "EOD_LOW_INDEX_VAL": 10807.1,
                "EOD_CLOSE_INDEX_VAL": 10910.1,
                "EOD_PREV_CLOSE": 10862.55,
                "EOD_TIMESTAMP": "01-Jan-2019",
            },
            {
                "EOD_OPEN_INDEX_VAL": 10868.85,
                "EOD_HIGH_INDEX_VAL": 10895.35,
                "EOD_LOW_INDEX_VAL": 10780.0,
                "EOD_CLOSE_INDEX_VAL": 10792.5,
                "EOD_PREV_CLOSE": 10910.1,
                "EOD_TIMESTAMP": "02-Jan-2019",
            },
        ]
    }
}


def _patch_client(monkeypatch, history_handler):
    """Replaces httpx.Client with one wired to a MockTransport, routing
    the session-handshake GET (to the bare domain) separately from the
    history-data GET (to /api/historicalOR/indicesHistory) — mirrors the
    two real requests NSEProvider.fetch_range makes."""
    calls = []

    def route(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if "/api/historicalOR/indicesHistory" in str(request.url):
            return history_handler(request)
        return httpx.Response(200, text="<html>ok</html>")  # the handshake GET

    real_client_cls = httpx.Client

    def client_factory(**kwargs):
        kwargs.pop("transport", None)
        return real_client_cls(transport=httpx.MockTransport(route), **kwargs)

    monkeypatch.setattr(httpx, "Client", client_factory)
    return calls


def test_fetch_range_returns_points_on_success(monkeypatch):
    def handler(request):
        return httpx.Response(200, json=REAL_SAMPLE_RESPONSE)

    _patch_client(monkeypatch, handler)
    points = NSEProvider().fetch_range("NIFTY 50", date(2019, 1, 1), date(2019, 1, 2))

    assert len(points) == 2
    assert points[0].price_date == date(2019, 1, 1)
    assert points[0].value == 10910.1
    assert points[1].price_date == date(2019, 1, 2)
    assert points[1].value == 10792.5


def test_fetch_range_sends_expected_query_params(monkeypatch):
    def handler(request):
        assert dict(request.url.params) == {
            "indexType": "NIFTY 50",
            "from": "01-01-2019",
            "to": "31-01-2019",
        }
        return httpx.Response(200, json=REAL_SAMPLE_RESPONSE)

    _patch_client(monkeypatch, handler)
    NSEProvider().fetch_range("NIFTY 50", date(2019, 1, 1), date(2019, 1, 31))


def test_fetch_range_performs_session_handshake_before_history_request(monkeypatch):
    def handler(request):
        return httpx.Response(200, json=REAL_SAMPLE_RESPONSE)

    calls = _patch_client(monkeypatch, handler)
    NSEProvider().fetch_range("NIFTY 50", date(2019, 1, 1), date(2019, 1, 2))

    assert len(calls) == 2
    assert "/api/historicalOR/indicesHistory" not in str(calls[0].url)
    assert "/api/historicalOR/indicesHistory" in str(calls[1].url)


def test_fetch_range_raises_on_http_error(monkeypatch):
    def handler(request):
        return httpx.Response(404, text="not found")

    _patch_client(monkeypatch, handler)
    with pytest.raises(BenchmarkProviderError, match="404"):
        NSEProvider().fetch_range("UNKNOWN INDEX", date(2019, 1, 1), date(2019, 1, 2))


def test_fetch_range_raises_on_non_json_response(monkeypatch):
    def handler(request):
        return httpx.Response(200, text="<html>not json</html>")

    _patch_client(monkeypatch, handler)
    with pytest.raises(BenchmarkProviderError, match="non-JSON"):
        NSEProvider().fetch_range("NIFTY 50", date(2019, 1, 1), date(2019, 1, 2))


def test_fetch_range_raises_on_unexpected_shape(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"unexpected": "shape"})

    _patch_client(monkeypatch, handler)
    with pytest.raises(BenchmarkProviderError, match="unexpected"):
        NSEProvider().fetch_range("NIFTY 50", date(2019, 1, 1), date(2019, 1, 2))


def test_fetch_range_raises_on_empty_records(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"data": {"indexCloseOnlineRecords": []}})

    _patch_client(monkeypatch, handler)
    with pytest.raises(BenchmarkProviderError, match="no historical data"):
        NSEProvider().fetch_range("NIFTY 50", date(2019, 1, 1), date(2019, 1, 2))


def test_fetch_range_skips_malformed_rows_but_keeps_valid_ones(monkeypatch):
    def handler(request):
        return httpx.Response(
            200,
            json={
                "data": {
                    "indexCloseOnlineRecords": [
                        {"EOD_TIMESTAMP": "not-a-date", "EOD_CLOSE_INDEX_VAL": 100.0},
                        {"EOD_TIMESTAMP": "01-Jan-2019", "EOD_CLOSE_INDEX_VAL": "not-a-number"},
                        {"EOD_TIMESTAMP": "02-Jan-2019", "EOD_CLOSE_INDEX_VAL": -5.0},
                        {"EOD_TIMESTAMP": "03-Jan-2019", "EOD_CLOSE_INDEX_VAL": 10910.1},
                    ]
                }
            },
        )

    _patch_client(monkeypatch, handler)
    points = NSEProvider().fetch_range("NIFTY 50", date(2019, 1, 1), date(2019, 1, 3))

    assert len(points) == 1
    assert points[0].price_date == date(2019, 1, 3)
    assert points[0].value == 10910.1


def test_fetch_range_retries_on_rate_limit_then_succeeds(monkeypatch):
    attempts = {"n": 0}

    def handler(request):
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(429, text="rate limited")
        return httpx.Response(200, json=REAL_SAMPLE_RESPONSE)

    _patch_client(monkeypatch, handler)
    points = NSEProvider().fetch_range("NIFTY 50", date(2019, 1, 1), date(2019, 1, 2))

    assert attempts["n"] == 2
    assert len(points) == 2


def test_served_benchmark_type_is_unset_since_it_depends_on_the_symbol_queried():
    # This endpoint serves both price and TRI index variants depending on
    # which index name (symbol) is queried — see nse.py's module
    # docstring — so it deliberately doesn't declare a fixed
    # served_benchmark_type the way a genuinely single-type provider would.
    assert NSEProvider.served_benchmark_type is None
