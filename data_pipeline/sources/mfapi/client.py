"""HTTP client for api.mfapi.in — a third-party aggregator that republishes
AMFI's own official NAV data, indexed for fast lookup of one scheme's full
NAV history by AMFI scheme code.

Response shape confirmed via a live GitHub Actions debug run against a
real onboarded scheme (see git history) — this sandbox itself cannot reach
external hosts to verify directly. A real request
(`GET https://api.mfapi.in/mf/135762`) returned:

    {
      "meta": {
        "fund_house": "Axis Mutual Fund", "scheme_type": "Open Ended Schemes",
        "scheme_category": "...", "scheme_code": 135762,
        "scheme_name": "Axis Children's Fund - Direct Plan - Growth Option",
        "isin_growth": "INF846K01WO1", "isin_div_reinvestment": null
      },
      "data": [{"date": "11-09-2026", "nav": "29.96280"}, ...],  # newest first
      "status": "SUCCESS"
    }

Used only for the on-demand, per-scheme historical backfill (see
data_pipeline/orchestration/lazy_nav_backfill.py) — NOT for daily
ingestion, which stays on AMFI's own NAVAll.txt as the primary source
(Rule 5: zero-budget, most-authoritative-available source first). mfapi.in
is a convenience layer over the same underlying AMFI data, used here
because it's the only verified source that returns one scheme's ENTIRE
history in a single request — AMFI's own historical report endpoint only
accepts a date range and always returns the whole fund universe for it,
which is what made a full universe-wide backfill (see git history) the
expensive alternative this replaces.
"""
from __future__ import annotations

import httpx

MFAPI_BASE_URL = "https://api.mfapi.in/mf"
DEFAULT_TIMEOUT_SECONDS = 30.0


class MfApiFetchError(RuntimeError):
    """Raised when a scheme's history cannot be downloaded from mfapi.in.

    Kept distinct from AMFI's NavFetchError so logs/error messages make
    clear which source failed, even though both mean the same thing
    operationally: this attempt produced no usable data.
    """


def fetch_scheme_history(amfi_code: str, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> dict:
    """Download one scheme's full NAV history as mfapi.in's raw JSON body.

    Raises MfApiFetchError on any network failure, timeout, non-2xx
    response, or a body that isn't the expected shape — never returns a
    partial/invalid result silently.
    """
    url = f"{MFAPI_BASE_URL}/{amfi_code}"
    try:
        response = httpx.get(url, timeout=timeout, follow_redirects=True)
        response.raise_for_status()
    except httpx.TimeoutException as exc:
        raise MfApiFetchError(f"Timed out fetching {url}") from exc
    except httpx.HTTPStatusError as exc:
        raise MfApiFetchError(f"mfapi.in returned HTTP {exc.response.status_code} for {url}") from exc
    except httpx.HTTPError as exc:
        raise MfApiFetchError(f"Network error fetching {url}: {exc}") from exc

    try:
        body = response.json()
    except ValueError as exc:
        raise MfApiFetchError(f"{url} returned non-JSON content") from exc

    if not isinstance(body, dict) or "data" not in body:
        raise MfApiFetchError(f"{url} returned an unexpected response shape")

    status = body.get("status")
    if status and status != "SUCCESS":
        raise MfApiFetchError(f"{url} reported status={status!r}")

    if not body["data"]:
        raise MfApiFetchError(f"{url} returned no NAV history (scheme code may not exist on mfapi.in)")

    return body
