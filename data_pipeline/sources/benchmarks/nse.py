"""NSE (nseindia.com) benchmark index provider — historical index-level
data via NSE's own "Historical Index Data" report API.

RESPONSE SHAPE — CONFIRMED (real sample, not a guess): a user of this
platform captured a real response from
`GET https://www.nseindia.com/api/historicalOR/indicesHistory` and pasted
it in. It looks like this:

    {
      "data": {
        "indexCloseOnlineRecords": [
          {
            "EOD_OPEN_INDEX_VAL": 10881.7,
            "EOD_HIGH_INDEX_VAL": 10923.6,
            "EOD_LOW_INDEX_VAL": 10807.1,
            "EOD_CLOSE_INDEX_VAL": 10910.1,
            "EOD_PREV_CLOSE": 10862.55,
            "EOD_TIMESTAMP": "01-Jan-2019"
          },
          ...
        ]
      }
    }

`_parse_response` below is written directly against this real shape, not
a guessed one — this supersedes an earlier version of this module that
guessed at niftyindices.com's ASP.NET-style endpoint and was never
confirmed against real output.

PRICE vs. TRI depends on WHICH INDEX YOU ASK FOR, not on this endpoint or
this response shape: the sample above happens to be for a plain price
index, but the same `indicesHistory` API returns the identical shape for
a TRI-named index too (e.g. querying `indexType="NIFTY 50 TRI"` rather
than `"NIFTY 50"`) — NSE publishes both price and Total Returns variants
as distinct named indices through this one endpoint. So
`served_benchmark_type` is left unset here (None = "depends on the
symbol queried, not fixed to one type") rather than hard-coded to
"PRICE"; lazy_benchmark_backfill.py's `_provider_matches_benchmark_type`
gate stays in place as reusable architecture (for a genuinely
single-type provider added later), but doesn't restrict this one.
Correctness instead depends on `Benchmark.symbol` naming the right
variant for a TRI benchmark — e.g. "NIFTY 50 TRI", not "NIFTY 50" — which
is unconfirmed against a real TRI-named response and is the next thing
worth checking (see docs/data-sources.md section 4). This is still in
service of the "never compare TRI against a price index without
explicitly handling the distinction" rule — the distinction is handled by
which symbol gets queried, not by refusing this provider outright.

REQUEST SHAPE — still a best-effort guess, unverified: nseindia.com is
known (from public documentation of similar tools, not from anything
confirmed for this project) to reject direct API calls without first
establishing session cookies from a normal page load, plus browser-like
headers and a Referer on the API call itself. `_ensure_session` below
follows that widely-documented pattern. The `from`/`to` request
parameter format and the exact `indexType` values NSE's dropdown accepts
(assumed to be the plain index name, e.g. "NIFTY 50") are inferred from
the confirmed response and have not themselves been confirmed by a real
request/response round trip — only the response *parsing* is confirmed.
See docs/data-sources.md section 4 for how this distinction is tracked.
"""
from __future__ import annotations

from datetime import date, datetime

import httpx

from data_pipeline.sources.benchmarks.base import BenchmarkPricePoint, BenchmarkProvider, BenchmarkProviderError

BASE_URL = "https://www.nseindia.com"
HISTORY_URL = f"{BASE_URL}/api/historicalOR/indicesHistory"
REFERER_URL = f"{BASE_URL}/reports-indices-historical-index-data"
DEFAULT_TIMEOUT_SECONDS = 30.0
MAX_RETRIES = 2

# A plain, real-browser-looking User-Agent — nseindia.com's anti-bot layer
# is known to reject requests carrying an obvious script/library identity
# (e.g. "python-requests/...").
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


class NSEProvider(BenchmarkProvider):
    name = "NSE"
    # served_benchmark_type intentionally left at the base class's default
    # (None) — see this module's docstring: this one endpoint serves both
    # price and TRI index variants depending on the symbol queried, so it
    # isn't fixed to a single benchmark_type the way served_benchmark_type
    # is meant to express.

    def __init__(self, base_url: str = BASE_URL, timeout: float = DEFAULT_TIMEOUT_SECONDS):
        self._base_url = base_url
        self._history_url = f"{base_url}/api/historicalOR/indicesHistory"
        self._timeout = timeout

    def _ensure_session(self, client: httpx.Client) -> None:
        """A bare GET to the API endpoint gets rejected without cookies
        first established by a normal page load — this loads the landing
        page (discarding its body) purely to receive those cookies onto
        `client`'s cookie jar before the real request."""
        try:
            response = client.get(self._base_url, headers={"Referer": self._base_url})
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise BenchmarkProviderError(f"NSE session handshake failed: {exc}") from exc

    def fetch_range(self, symbol: str, start: date, end: date) -> list[BenchmarkPricePoint]:
        params = {
            "indexType": symbol,
            "from": start.strftime("%d-%m-%Y"),
            "to": end.strftime("%d-%m-%Y"),
        }

        last_error: Exception | None = None
        with httpx.Client(timeout=self._timeout, headers=_BROWSER_HEADERS, follow_redirects=True) as client:
            self._ensure_session(client)

            for _attempt in range(MAX_RETRIES + 1):
                try:
                    response = client.get(self._history_url, params=params, headers={"Referer": REFERER_URL})
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

        data = body.get("data") if isinstance(body, dict) else None
        rows = data.get("indexCloseOnlineRecords") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            raise BenchmarkProviderError(f"NSE returned an unexpected response shape for {symbol!r}")
        if not rows:
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
        raw = row.get("EOD_TIMESTAMP")
        if not raw:
            return None
        try:
            return datetime.strptime(str(raw).strip(), "%d-%b-%Y").date()
        except ValueError:
            return None

    @staticmethod
    def _extract_value(row: dict) -> float | None:
        raw = row.get("EOD_CLOSE_INDEX_VAL")
        if raw is None:
            return None
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return None
        return value if value > 0 else None
