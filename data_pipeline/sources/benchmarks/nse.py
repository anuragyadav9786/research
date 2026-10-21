"""NSE Indices Limited's own "Historical Total Returns Index" data —
served via niftyindices.com (the organization that defines and publishes
every Nifty-branded index), not nseindia.com directly.

CONFIRMED against real live round trips this session (not a guess):

    POST https://www.niftyindices.com/BackPage/getTotalReturnIndexString
        {"cinfo": "{'name':'Nifty 100','startDate':'01-Oct-2026','endDate':'19-Oct-2026','indexName':'Nifty 100'}"}
        -> [{"RequestNumber": "...", "Index Name": "Nifty 100",
             "Date": "19 Oct 2026", "TotalReturnsIndex": "33165.00",
             "NTR_Value": "-"}, ...]

Two confirmed details that aren't obvious from the endpoint's own naming:

1. `name`/`indexName` must be the BASE index name, with no "TRI" suffix
   (e.g. "Nifty 100", not "Nifty 100 TRI") -- querying with "TRI" in the
   name returns an empty list. `_to_base_index_name` strips it.
2. The endpoint always returns the Total Returns Index value (field
   `TotalReturnsIndex`) for whatever base name is queried -- there's no
   separate "give me the plain price index" mode here, so this provider
   is unconditionally TRI-only (`served_benchmark_type = "TRI"`), unlike
   a prior, now-replaced version of this module that guessed at
   nseindia.com's own API (confirmed this session to return HTTP 403 --
   blocked, not a transient failure) and had to stay type-agnostic
   because that endpoint serves both price and TRI variants.

An unrecognized index name returns an empty list (not an error) --
confirmed live -- so a custom blended-index benchmark (e.g. a scheme's
AMC-disclosed "35% BSE Oil & Gas Index +30%...") correctly surfaces as
"no data" (BenchmarkProviderError below) rather than silently matching
the wrong series.

No session/cookie handshake is needed -- confirmed via a direct POST
round trip, unlike nseindia.com's own API.
"""
from __future__ import annotations

import re
from datetime import date, datetime

import httpx

from data_pipeline.sources.benchmarks.base import BenchmarkPricePoint, BenchmarkProvider, BenchmarkProviderError

BASE_URL = "https://www.niftyindices.com"
HISTORY_URL = f"{BASE_URL}/BackPage/getTotalReturnIndexString"
DEFAULT_TIMEOUT_SECONDS = 30.0
MAX_RETRIES = 2

_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "*/*",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Origin": BASE_URL,
    "Referer": f"{BASE_URL}/reports/historical-data",
}

_TRI_SUFFIX_RE = re.compile(r"\s+tri$", re.IGNORECASE)


def _to_base_index_name(symbol: str) -> str:
    """"Nifty 100 TRI" -> "Nifty 100" -- confirmed live: this endpoint only
    recognizes the base name, and always returns the TRI value for it."""
    return _TRI_SUFFIX_RE.sub("", symbol.strip())


class NSEProvider(BenchmarkProvider):
    name = "NSE"
    # Confirmed fixed: every successful response carries the Total
    # Returns Index value, unconditionally -- see module docstring.
    served_benchmark_type = "TRI"

    def __init__(self, base_url: str = BASE_URL, timeout: float = DEFAULT_TIMEOUT_SECONDS):
        self._history_url = f"{base_url}/BackPage/getTotalReturnIndexString"
        self._timeout = timeout

    def fetch_range(self, symbol: str, start: date, end: date) -> list[BenchmarkPricePoint]:
        base_name = _to_base_index_name(symbol)
        payload = {
            "cinfo": (
                "{'name':'%s','startDate':'%s','endDate':'%s','indexName':'%s'}"
                % (base_name, start.strftime("%d-%b-%Y"), end.strftime("%d-%b-%Y"), base_name)
            )
        }

        last_error: Exception | None = None
        with httpx.Client(timeout=self._timeout, headers=_HEADERS) as client:
            for _attempt in range(MAX_RETRIES + 1):
                try:
                    response = client.post(self._history_url, json=payload)
                    response.raise_for_status()
                    return self._parse_response(response, symbol)
                except httpx.TimeoutException as exc:
                    last_error = exc
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 429:
                        last_error = exc  # rate-limited — worth a retry
                    else:
                        raise BenchmarkProviderError(
                            f"niftyindices.com returned HTTP {exc.response.status_code} for {symbol!r}"
                        ) from exc
                except httpx.HTTPError as exc:
                    last_error = exc

        raise BenchmarkProviderError(
            f"niftyindices.com fetch failed for {symbol!r} after {MAX_RETRIES + 1} attempts: {last_error}"
        ) from last_error

    def _parse_response(self, response: httpx.Response, symbol: str) -> list[BenchmarkPricePoint]:
        try:
            rows = response.json()
        except ValueError as exc:
            raise BenchmarkProviderError(f"niftyindices.com returned non-JSON content for {symbol!r}") from exc

        if not isinstance(rows, list):
            raise BenchmarkProviderError(f"niftyindices.com returned an unexpected response shape for {symbol!r}")
        if not rows:
            # Confirmed live: an unrecognized index name returns [], not an
            # error -- e.g. a custom blended-index benchmark name that
            # doesn't match any real Nifty-branded index.
            raise BenchmarkProviderError(f"niftyindices.com returned no historical data for {symbol!r}")

        points: list[BenchmarkPricePoint] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            row_date = self._extract_date(row)
            row_value = self._extract_value(row)
            if row_date is not None and row_value is not None:
                points.append(BenchmarkPricePoint(price_date=row_date, value=row_value))

        if not points:
            raise BenchmarkProviderError(f"niftyindices.com response for {symbol!r} contained no usable rows")

        return points

    @staticmethod
    def _extract_date(row: dict) -> date | None:
        raw = row.get("Date")
        if not raw:
            return None
        try:
            return datetime.strptime(str(raw).strip(), "%d %b %Y").date()
        except ValueError:
            return None

    @staticmethod
    def _extract_value(row: dict) -> float | None:
        raw = row.get("TotalReturnsIndex")
        if raw is None:
            return None
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return None
        return value if value > 0 else None
