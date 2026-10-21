"""Tests for the NSE (niftyindices.com) benchmark provider's HTTP client,
using a mocked transport — no real network access in this test run. The
request/response shape below is REAL, confirmed via live round trips
against https://www.niftyindices.com/BackPage/getTotalReturnIndexString
this session (see nse.py's module docstring) — not a guess, and not the
nseindia.com endpoint an earlier version of this module used (confirmed
this session to return HTTP 403, blocked)."""
import json
from datetime import date

import httpx
import pytest

from data_pipeline.sources.benchmarks.base import BenchmarkProviderError
from data_pipeline.sources.benchmarks.nse import NSEProvider, _to_base_index_name

REAL_SAMPLE_RESPONSE = [
    {
        "RequestNumber": "TRI63928183571956896000",
        "Index Name": "Nifty 50",
        "Date": "19 Oct 2026",
        "TotalReturnsIndex": "34787.78",
        "NTR_Value": "30206.08",
    },
    {
        "RequestNumber": "TRI63928183571956896000",
        "Index Name": "Nifty 50",
        "Date": "16 Oct 2026",
        "TotalReturnsIndex": "35178.68",
        "NTR_Value": "30545.51",
    },
]


def _patch_client(monkeypatch, handler):
    calls = []

    def route(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return handler(request)

    real_client_cls = httpx.Client

    def client_factory(**kwargs):
        kwargs.pop("transport", None)
        return real_client_cls(transport=httpx.MockTransport(route), **kwargs)

    monkeypatch.setattr(httpx, "Client", client_factory)
    return calls


def test_to_base_index_name_strips_tri_suffix_case_insensitively():
    assert _to_base_index_name("Nifty 100 TRI") == "Nifty 100"
    assert _to_base_index_name("NIFTY 500 tri") == "NIFTY 500"
    assert _to_base_index_name("Nifty 50") == "Nifty 50"  # no suffix to strip


def test_fetch_range_returns_points_on_success(monkeypatch):
    def handler(request):
        return httpx.Response(200, json=REAL_SAMPLE_RESPONSE)

    _patch_client(monkeypatch, handler)
    points = NSEProvider().fetch_range("Nifty 50 TRI", date(2026, 10, 16), date(2026, 10, 19))

    assert len(points) == 2
    assert points[0].price_date == date(2026, 10, 19)
    assert points[0].value == 34787.78
    assert points[1].price_date == date(2026, 10, 16)
    assert points[1].value == 35178.68


def test_fetch_range_sends_base_name_without_tri_suffix(monkeypatch):
    def handler(request):
        body = json.loads(request.content)
        cinfo = body["cinfo"]
        assert "'name':'Nifty 50'" in cinfo
        assert "'indexName':'Nifty 50'" in cinfo
        assert "TRI" not in cinfo.split("'startDate'")[0]  # name field has no TRI
        assert "'startDate':'01-Oct-2026'" in cinfo
        assert "'endDate':'19-Oct-2026'" in cinfo
        return httpx.Response(200, json=REAL_SAMPLE_RESPONSE)

    _patch_client(monkeypatch, handler)
    NSEProvider().fetch_range("Nifty 50 TRI", date(2026, 10, 1), date(2026, 10, 19))


def test_fetch_range_makes_a_single_direct_post_no_handshake(monkeypatch):
    def handler(request):
        return httpx.Response(200, json=REAL_SAMPLE_RESPONSE)

    calls = _patch_client(monkeypatch, handler)
    NSEProvider().fetch_range("Nifty 50 TRI", date(2026, 10, 16), date(2026, 10, 19))

    assert len(calls) == 1
    assert "getTotalReturnIndexString" in str(calls[0].url)


def test_fetch_range_raises_on_http_error(monkeypatch):
    def handler(request):
        return httpx.Response(404, text="not found")

    _patch_client(monkeypatch, handler)
    with pytest.raises(BenchmarkProviderError, match="404"):
        NSEProvider().fetch_range("Unknown Index TRI", date(2026, 10, 16), date(2026, 10, 19))


def test_fetch_range_raises_on_non_json_response(monkeypatch):
    def handler(request):
        return httpx.Response(200, text="<html>not json</html>")

    _patch_client(monkeypatch, handler)
    with pytest.raises(BenchmarkProviderError, match="non-JSON"):
        NSEProvider().fetch_range("Nifty 50 TRI", date(2026, 10, 16), date(2026, 10, 19))


def test_fetch_range_raises_on_unexpected_shape(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"unexpected": "shape"})

    _patch_client(monkeypatch, handler)
    with pytest.raises(BenchmarkProviderError, match="unexpected"):
        NSEProvider().fetch_range("Nifty 50 TRI", date(2026, 10, 16), date(2026, 10, 19))


def test_fetch_range_raises_on_empty_list_unrecognized_index(monkeypatch):
    """Confirmed live: an unrecognized index name (e.g. a custom
    blended-index benchmark name) returns [], not an error -- the
    provider still surfaces this as "no data" rather than a crash."""

    def handler(request):
        return httpx.Response(200, json=[])

    _patch_client(monkeypatch, handler)
    with pytest.raises(BenchmarkProviderError, match="no historical data"):
        NSEProvider().fetch_range("Some Custom Blended Index", date(2026, 10, 16), date(2026, 10, 19))


def test_fetch_range_skips_malformed_rows_but_keeps_valid_ones(monkeypatch):
    def handler(request):
        return httpx.Response(
            200,
            json=[
                {"Date": "not-a-date", "TotalReturnsIndex": "100.0"},
                {"Date": "16 Oct 2026", "TotalReturnsIndex": "not-a-number"},
                {"Date": "17 Oct 2026", "TotalReturnsIndex": "-5.0"},
                {"Date": "19 Oct 2026", "TotalReturnsIndex": "34787.78"},
            ],
        )

    _patch_client(monkeypatch, handler)
    points = NSEProvider().fetch_range("Nifty 50 TRI", date(2026, 10, 16), date(2026, 10, 19))

    assert len(points) == 1
    assert points[0].price_date == date(2026, 10, 19)
    assert points[0].value == 34787.78


def test_fetch_range_retries_on_rate_limit_then_succeeds(monkeypatch):
    attempts = {"n": 0}

    def handler(request):
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(429, text="rate limited")
        return httpx.Response(200, json=REAL_SAMPLE_RESPONSE)

    _patch_client(monkeypatch, handler)
    points = NSEProvider().fetch_range("Nifty 50 TRI", date(2026, 10, 16), date(2026, 10, 19))

    assert attempts["n"] == 2
    assert len(points) == 2


def test_served_benchmark_type_is_fixed_to_tri():
    # Confirmed live: this endpoint always returns the Total Returns Index
    # value regardless of the queried base name -- unlike the old
    # nseindia.com endpoint this replaced, which served both price and TRI
    # variants depending on the symbol queried.
    assert NSEProvider.served_benchmark_type == "TRI"
