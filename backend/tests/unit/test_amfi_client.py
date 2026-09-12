"""Tests for the AMFI HTTP client's error handling, using a mocked
transport — no real network access (this sandbox blocks amfiindia.com
outbound; see client.py's module docstring)."""
import httpx
import pytest

from data_pipeline.sources.amfi.client import NavFetchError, fetch_navall


def _client_with_response(handler) -> httpx.Client:
    transport = httpx.MockTransport(handler)
    return httpx.Client(transport=transport)


def test_fetch_navall_returns_body_on_success(monkeypatch):
    def handler(request):
        return httpx.Response(200, text="Scheme Code;...\n900001;...;100.00;12-Sep-2026")

    monkeypatch.setattr(httpx, "get", lambda url, timeout, follow_redirects: _client_with_response(handler).get(url))
    text = fetch_navall(url="https://example.invalid/NAVAll.txt")
    assert "900001" in text


def test_fetch_navall_raises_on_http_error(monkeypatch):
    def handler(request):
        return httpx.Response(503, text="Service Unavailable")

    monkeypatch.setattr(httpx, "get", lambda url, timeout, follow_redirects: _client_with_response(handler).get(url))
    with pytest.raises(NavFetchError, match="503"):
        fetch_navall(url="https://example.invalid/NAVAll.txt")


def test_fetch_navall_raises_on_timeout(monkeypatch):
    def raise_timeout(url, timeout, follow_redirects):
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(httpx, "get", raise_timeout)
    with pytest.raises(NavFetchError, match="Timed out"):
        fetch_navall(url="https://example.invalid/NAVAll.txt")


def test_fetch_navall_raises_on_empty_body(monkeypatch):
    def handler(request):
        return httpx.Response(200, text="   ")

    monkeypatch.setattr(httpx, "get", lambda url, timeout, follow_redirects: _client_with_response(handler).get(url))
    with pytest.raises(NavFetchError, match="empty"):
        fetch_navall(url="https://example.invalid/NAVAll.txt")
