"""HTTP client for Financial Benchmarks India Ltd's (FBIL) T-Bill
benchmark-rate feed -- replaces the hardcoded Settings.risk_free_rate =
0.07 placeholder (docs/data-sources.md's open decision #4) with the real
rate used across every Sharpe/Sortino computation.

FBIL (fbil.org.in) is the RBI-recognized administrator of India's
official T-Bill benchmark rates (listed among RBI's "significant
benchmarks"), published daily and referenced by real lenders for
rate-linked loan products. This platform conventionally calls that rate
the "risk-free rate" and has historically labelled it a "91-day T-bill
rate" (Settings.risk_free_rate's own docstring) -- FBIL does not publish
a literal "91 Days" tenor, only discrete monthly tenors (1/2/.../12
months), so the "3 Months" tenor (~91 days) is used as the standard
market-convention equivalent. This is a real, named tenor from the
confirmed response below, not a guess.

Endpoint confirmed via a real live round trip this session (2026-11-03),
from BOTH a headless-browser fetch and a direct httpx.get() from this
same backend environment -- unlike amfiindia.com/NSE's old endpoint,
this host is NOT network-blocked from the backend process itself:

    GET https://www.fbil.org.in/wasdm/tbill/fetch?authenticated=false

    [
      {"processRunDate": "2026-10-26 00:00:00", "displayTime": "2026-10-26 17:30:00",
       "tenorName": "3 Months", "rate": 5.870000, "comments": " "},
      ...
    ]

Confirmed shape: a flat JSON array (no wrapper object), each row one
(date, tenor, rate) triple. `rate` is already a plain percentage (5.87
means 5.87%, not 0.0587). The endpoint returns only the most recently
published business day or two (28 rows = 14 tenors x 2 dates in the
confirmed response) -- it is NOT a full historical series, consistent
with how this platform only ever needs the CURRENT rate (every
Sharpe/Sortino call site takes a single risk_free_rate_annual, never a
time-indexed series). Discovered via this endpoint's own frontend
(fbil.org.in's T-Bill chart calls it as `fetch?authenticated=false`),
not from any published API documentation -- FBIL does not publish one --
so this client defends against the response shape changing (missing
keys, no "3 Months" row, non-numeric rate) by raising rather than
guessing, same as mfapi/client.py's own contract.
"""
from __future__ import annotations

from datetime import date, datetime

import httpx

FBIL_TBILL_URL = "https://www.fbil.org.in/wasdm/tbill/fetch?authenticated=false"
DEFAULT_TIMEOUT_SECONDS = 15.0
TARGET_TENOR_NAME = "3 Months"  # the market-conventional ~91-day equivalent -- see module docstring


class FbilFetchError(RuntimeError):
    """Raised when the current T-Bill rate can't be downloaded or parsed
    from FBIL -- never returns a partial/invalid result silently."""


def fetch_latest_3m_tbill_rate_pct(timeout: float = DEFAULT_TIMEOUT_SECONDS) -> tuple[date, float]:
    """(as_of_date, rate_pct) for the most recently published "3 Months"
    T-Bill benchmark rate. rate_pct is a plain percentage (e.g. 5.87).
    Raises FbilFetchError on any network failure, timeout, non-2xx
    response, or a body that isn't the expected shape."""
    try:
        response = httpx.get(FBIL_TBILL_URL, timeout=timeout, follow_redirects=True)
        response.raise_for_status()
    except httpx.TimeoutException as exc:
        raise FbilFetchError(f"Timed out fetching {FBIL_TBILL_URL}") from exc
    except httpx.HTTPStatusError as exc:
        raise FbilFetchError(f"FBIL returned HTTP {exc.response.status_code} for {FBIL_TBILL_URL}") from exc
    except httpx.HTTPError as exc:
        raise FbilFetchError(f"Network error fetching {FBIL_TBILL_URL}: {exc}") from exc

    try:
        rows = response.json()
    except ValueError as exc:
        raise FbilFetchError(f"{FBIL_TBILL_URL} returned non-JSON content") from exc

    if not isinstance(rows, list) or not rows:
        raise FbilFetchError(f"{FBIL_TBILL_URL} returned an unexpected response shape")

    three_month_rows = [r for r in rows if isinstance(r, dict) and r.get("tenorName") == TARGET_TENOR_NAME]
    if not three_month_rows:
        raise FbilFetchError(f"{FBIL_TBILL_URL} returned no {TARGET_TENOR_NAME!r} tenor row")

    def _parse_date(row: dict) -> date | None:
        try:
            return datetime.strptime(row["processRunDate"], "%Y-%m-%d %H:%M:%S").date()
        except (KeyError, ValueError, TypeError):
            return None

    dated_rows = [(_parse_date(r), r) for r in three_month_rows]
    dated_rows = [(d, r) for d, r in dated_rows if d is not None]
    if not dated_rows:
        raise FbilFetchError(f"{FBIL_TBILL_URL} rows had no parseable processRunDate")

    latest_date, latest_row = max(dated_rows, key=lambda dr: dr[0])

    try:
        rate_pct = float(latest_row["rate"])
    except (KeyError, TypeError, ValueError) as exc:
        raise FbilFetchError(f"{FBIL_TBILL_URL} row had a non-numeric rate: {latest_row!r}") from exc
    if rate_pct <= 0:
        raise FbilFetchError(f"{FBIL_TBILL_URL} returned a non-positive rate: {rate_pct!r}")

    return latest_date, rate_pct
