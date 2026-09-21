"""NSE (via niftyindices.com) benchmark index provider.

Covers the Nifty TRI family (Nifty 50 TRI, Nifty 100 TRI, Nifty Midcap 150
TRI, ...) — the actual benchmark class most equity scheme benchmarks in
this platform's data use (see Benchmark.benchmark_type). Plain NSE bhavcopy
(archives.nseindia.com) is deliberately NOT used here: bhavcopy only carries
price-return index levels, not the dividend-reinvested Total Returns Index
values a fund's benchmark actually needs — conflating the two would compare
a fund's total return against a benchmark that silently excludes dividends,
which is exactly the "never compare TRI against a price index without
explicitly handling the distinction" rule this engine exists to uphold.

IMPORTANT — unverified against a live response: this sandbox has no
outbound network access at all (confirmed via an explicit 403
organization-policy denial on niftyindices.com — not a transient
failure; see data_pipeline/sources/mfapi/client.py's docstring for the
equivalent situation there, verified instead via a live CI run this
environment has no way to reproduce). The request/response shape below
follows the endpoint niftyindices.com's own historical-data page uses
(widely documented in open-source Indian-market tooling), but has NOT
been confirmed against a live response from any environment. It is
nonetheless enabled by default (Settings.benchmark_nse_provider_enabled
= True): validate_benchmark_points rejects anything malformed, and a
shape mismatch here fails a fetch attempt closed (falls back to cache or
"Data unavailable"), never returns a fabricated value — so shipping it
enabled-but-unconfirmed does not risk showing a wrong number, only a
missing one until someone with real network access confirms this against
the live endpoint. See docs/data-sources.md section 4.

Expected request:
    POST https://www.niftyindices.com/Backpage.aspx/getHistoricaldatatabletoString
    Content-Type: application/json
    {"name": "<symbol>", "startDate": "DD-Mon-YYYY", "endDate": "DD-Mon-YYYY"}

Expected response body (ASP.NET-style: the real payload is a JSON string
nested inside the "d" field):
    {"d": "[{\\"EOD_CLOSE_INDEX_VAL\\": \\"28431.25\\", \\"HistoricalDate\\": \\"02-Jan-2025\\", ...}, ...]"}
"""
from __future__ import annotations

import json
from datetime import date, datetime

import httpx

from data_pipeline.sources.benchmarks.base import BenchmarkPricePoint, BenchmarkProvider, BenchmarkProviderError

NIFTY_INDICES_URL = "https://www.niftyindices.com/Backpage.aspx/getHistoricaldatatabletoString"
DEFAULT_TIMEOUT_SECONDS = 30.0
MAX_RETRIES = 2

# The response's per-row date/value keys are not perfectly consistent
# across niftyindices.com's own historical export formats (TRI vs. price
# series use slightly different column names) — tried in order.
_DATE_KEYS = ("HistoricalDate", "Date")
_VALUE_KEYS = ("EOD_CLOSE_INDEX_VAL", "Close", "CLOSE")


class NSEProvider(BenchmarkProvider):
    name = "NSE"

    def __init__(self, base_url: str = NIFTY_INDICES_URL, timeout: float = DEFAULT_TIMEOUT_SECONDS):
        self._base_url = base_url
        self._timeout = timeout

    def fetch_range(self, symbol: str, start: date, end: date) -> list[BenchmarkPricePoint]:
        payload = {
            "name": symbol,
            "startDate": start.strftime("%d-%b-%Y"),
            "endDate": end.strftime("%d-%b-%Y"),
        }

        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = httpx.post(
                    self._base_url,
                    json=payload,
                    timeout=self._timeout,
                    headers={"Content-Type": "application/json", "Accept": "application/json"},
                )
                response.raise_for_status()
                return self._parse_response(response, symbol)
            except httpx.TimeoutException as exc:
                last_error = exc
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    last_error = exc  # rate-limited — worth a retry
                else:
                    raise BenchmarkProviderError(
                        f"NSE returned HTTP {exc.response.status_code} for {symbol!r}"
                    ) from exc
            except httpx.HTTPError as exc:
                last_error = exc

        raise BenchmarkProviderError(
            f"NSE fetch failed for {symbol!r} after {MAX_RETRIES + 1} attempts: {last_error}"
        ) from last_error

    def _parse_response(self, response: httpx.Response, symbol: str) -> list[BenchmarkPricePoint]:
        try:
            body = response.json()
        except ValueError as exc:
            raise BenchmarkProviderError(f"NSE returned non-JSON content for {symbol!r}") from exc

        rows_raw = body.get("d") if isinstance(body, dict) else None
        if rows_raw is None:
            raise BenchmarkProviderError(f"NSE returned an unexpected response shape for {symbol!r}")

        try:
            rows = json.loads(rows_raw) if isinstance(rows_raw, str) else rows_raw
        except ValueError as exc:
            raise BenchmarkProviderError(f"NSE returned a malformed inner payload for {symbol!r}") from exc

        if not isinstance(rows, list) or not rows:
            raise BenchmarkProviderError(f"NSE returned no historical data for {symbol!r}")

        points: list[BenchmarkPricePoint] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            row_date = self._extract_date(row)
            row_value = self._extract_value(row)
            if row_date is not None and row_value is not None:
                points.append(BenchmarkPricePoint(price_date=row_date, value=row_value))

        if not points:
            raise BenchmarkProviderError(f"NSE response for {symbol!r} contained no usable rows")

        return points

    @staticmethod
    def _extract_date(row: dict) -> date | None:
        for key in _DATE_KEYS:
            raw = row.get(key)
            if raw:
                for fmt in ("%d-%b-%Y", "%d-%m-%Y"):
                    try:
                        return datetime.strptime(str(raw).strip(), fmt).date()
                    except ValueError:
                        continue
        return None

    @staticmethod
    def _extract_value(row: dict) -> float | None:
        for key in _VALUE_KEYS:
            raw = row.get(key)
            if raw is None:
                continue
            try:
                value = float(str(raw).replace(",", "").strip())
            except ValueError:
                continue
            if value > 0:
                return value
        return None
