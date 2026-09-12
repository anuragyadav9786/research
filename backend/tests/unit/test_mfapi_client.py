"""Tests for the mfapi.in HTTP client's error handling, using a mocked
transport — no real network access (this sandbox has no outbound internet
access at all; see client.py's module docstring for the real response
shape this was verified against)."""
import httpx
import pytest

from data_pipeline.sources.mfapi.client import MfApiFetchError, fetch_scheme_history


def _client_with_response(handler) -> httpx.Client:
    transport = httpx.MockTransport(handler)
    return httpx.Client(transport=transport)


def _patch_get(monkeypatch, handler):
    monkeypatch.setattr(
        httpx, "get", lambda url, timeout, follow_redirects: _client_with_response(handler).get(url)
    )


def test_fetch_scheme_history_returns_body_on_success(monkeypatch):
    def handler(request):
        return httpx.Response(
            200,
            json={
                "meta": {"scheme_code": 135762, "scheme_name": "Sample Fixture Fund"},
                "data": [{"date": "11-09-2026", "nav": "29.96280"}],
                "status": "SUCCESS",
            },
        )

    _patch_get(monkeypatch, handler)
    body = fetch_scheme_history("135762")
    assert body["meta"]["scheme_code"] == 135762
    assert len(body["data"]) == 1


def test_fetch_scheme_history_raises_on_http_error(monkeypatch):
    def handler(request):
        return httpx.Response(503, text="Service Unavailable")

    _patch_get(monkeypatch, handler)
    with pytest.raises(MfApiFetchError, match="503"):
        fetch_scheme_history("135762")


def test_fetch_scheme_history_raises_on_timeout(monkeypatch):
    def raise_timeout(url, timeout, follow_redirects):
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(httpx, "get", raise_timeout)
    with pytest.raises(MfApiFetchError, match="Timed out"):
        fetch_scheme_history("135762")


def test_fetch_scheme_history_raises_on_empty_data(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"meta": {}, "data": [], "status": "SUCCESS"})

    _patch_get(monkeypatch, handler)
    with pytest.raises(MfApiFetchError, match="no NAV history"):
        fetch_scheme_history("999999999")


def test_fetch_scheme_history_raises_on_non_success_status(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"meta": {}, "data": [{"date": "01-01-2020", "nav": "10"}], "status": "FAILED"})

    _patch_get(monkeypatch, handler)
    with pytest.raises(MfApiFetchError, match="FAILED"):
        fetch_scheme_history("135762")


def test_fetch_scheme_history_raises_on_unexpected_shape(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"unexpected": "shape"})

    _patch_get(monkeypatch, handler)
    with pytest.raises(MfApiFetchError, match="unexpected"):
        fetch_scheme_history("135762")
