"""Client + parser for AMFI's portal "Download NAV History Report"
endpoint — a DIFFERENT real source from NAVAll.txt (client.py/parser.py
in this same package), used here to fetch ONE SPECIFIC PAST DATE's
whole-universe NAV snapshot, which NAVAll.txt cannot do (it only ever
serves "today").

CONFIRMED against a real, live round trip in this session (this sandbox
has outbound access to portal.amfiindia.com, unlike amfiindia.com's other
endpoints tried earlier in this project's history):

    GET https://portal.amfiindia.com/DownloadNAVHistoryReport_Po.aspx
        ?tp=1&frmdt=19-Oct-2026

returned a real semicolon-delimited file, 8,556 real data rows for that
one date. Passing `todt` too returns every day in that range for the
whole universe in one request (confirmed: a 19-day range returned 109,929
rows) — not used here, since the fund screener (data_pipeline/
orchestration/period_return_rollup.py) only ever needs ONE date at a
time (today, or one lookback anchor), not a continuous range.

Real confirmed column layout — NOTE this is a DIFFERENT column order
from NAVAll.txt's (see parser.py's docstring for that one; the two are
easy to confuse since both are 8-field, semicolon-delimited, AMFI-hosted
files with the same category-header/AMC-name-line interleaving):

    Scheme Code;NAV Name;Plan;Option;ISIN Div Payout/ISIN Growth;ISIN Div Reinvestment;Net Asset Value;Date

    Open Ended Schemes ( Equity Scheme - Multi Cap Fund )


    Aditya Birla Sun Life Mutual Fund
    148921;Aditya Birla Sun Life Multi-Cap Fund-Direct Growth;Direct Plan;GROWTH;INF209KB1Y49;;21.73;19-Oct-2026

This module only extracts Scheme Code -> NAV, deliberately ignoring
Plan/Option/category here: the caller already knows exactly which
scheme_codes (amfi_codes) it cares about, precomputed once from this
platform's own scheme_variants/schemes tables (see
period_return_rollup.py), so there is no need to re-derive plan/option/
category from this file at all.
"""
from __future__ import annotations

from datetime import date

import httpx

PORTAL_HISTORY_URL = "https://portal.amfiindia.com/DownloadNAVHistoryReport_Po.aspx"
DEFAULT_TIMEOUT_SECONDS = 60.0
_FIELD_COUNT = 8
_SCHEME_CODE_FIELD = 0
_NAV_FIELD = 6


class PortalHistoryFetchError(RuntimeError):
    """Raised when a single date's portal NAV history snapshot cannot be
    downloaded or is empty — distinct from a generic exception so the
    rollup orchestration can catch it specifically and fall back to an
    earlier date (see period_return_rollup.py's step-back-over-holidays
    logic), the same way NavFetchError is used in client.py.
    """


def fetch_portal_history_for_date(
    target_date: date, url: str = PORTAL_HISTORY_URL, timeout: float = DEFAULT_TIMEOUT_SECONDS
) -> str:
    """Download the raw NAV history report for exactly one date (no
    `todt`, so AMFI returns only `frmdt`'s single date). Raises
    PortalHistoryFetchError on any network failure, timeout, non-2xx
    response, or an empty body.
    """
    params = {"tp": "1", "frmdt": target_date.strftime("%d-%b-%Y")}
    try:
        response = httpx.get(url, params=params, timeout=timeout, follow_redirects=True)
        response.raise_for_status()
    except httpx.TimeoutException as exc:
        raise PortalHistoryFetchError(f"Timed out fetching {url} for {target_date}") from exc
    except httpx.HTTPStatusError as exc:
        raise PortalHistoryFetchError(
            f"AMFI portal returned HTTP {exc.response.status_code} for {target_date}"
        ) from exc
    except httpx.HTTPError as exc:
        raise PortalHistoryFetchError(f"Network error fetching {url} for {target_date}: {exc}") from exc

    text = response.text
    if not text or not text.strip():
        raise PortalHistoryFetchError(f"{url} returned an empty response body for {target_date}")
    return text


def parse_portal_history_navs(raw_text: str) -> dict[str, float]:
    """Parse a portal history snapshot into {scheme_code: nav}.

    Permissive about structure (category/AMC header lines, blank lines —
    same interleaving NAVAll.txt has), but a row whose NAV can't be
    parsed as a positive float is silently excluded rather than raising —
    this mirrors nav_validation.py's "reject the bad row, don't fail the
    whole run" convention, appropriate here since a handful of malformed
    rows in an 8,000+ row file is expected, not exceptional.
    """
    navs: dict[str, float] = {}

    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line or ";" not in line:
            continue
        if line.lower().startswith("scheme code;"):
            continue  # column header row

        fields = line.split(";")
        if len(fields) != _FIELD_COUNT:
            continue

        scheme_code = fields[_SCHEME_CODE_FIELD].strip()
        if not scheme_code:
            continue

        try:
            nav = float(fields[_NAV_FIELD].strip())
        except ValueError:
            continue
        if nav <= 0:
            continue

        navs[scheme_code] = nav

    return navs
