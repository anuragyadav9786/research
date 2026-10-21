"""Client for AMFI's "Fund Performance" Angular app's real backend API —
a different, newer real source from both NAVAll.txt (client.py) and the
portal history snapshot endpoint (portal_history.py).

CONFIRMED against real live round trips in this session: the page at
https://www.amfiindia.com/otherdata/fund-performance embeds an iframe
pointing at https://www.amfiindia.com/polling/amfi/fund-performance (an
Angular SPA), whose own JS bundle calls these same-origin endpoints
(traced through its minified source, then replayed and confirmed via
plain curl — no browser needed despite the app itself being Angular):

    POST https://www.amfiindia.com/gateway/pollingsebi/api/amfi/fundperformancefilters
        {} -> {"data": {"maturityTypeList": [...], "investmentTypeList": [...], "mutualFundList": [...]}}

    POST https://www.amfiindia.com/gateway/pollingsebi/api/amfi/getsubcategory
        {"category": 1} -> {"data": [{"name": "Large Cap", "id": 1}, ...]}
        (14 real subcategories confirmed for category=1/Equity)

    POST https://www.amfiindia.com/gateway/pollingsebi/api/amfi/fundperformance
        {"maturityType": 1, "category": 1, "subCategory": 1, "mfid": 0, "reportDate": "19-Oct-2026"}
        -> {"data": [{"schemeName": "...", "benchmark": "Nifty 100 TRI", "return1YearRegular": ..., ...}]}
        (mfid=0 confirmed to mean "every AMC", not a single one — 35 real
        schemes returned for Large Cap across many different AMCs)

Note the underlying infrastructure (polling.crisil.com, per the Angular
app's own runtime config.json) rejected direct requests even with
matching Origin/Referer headers — but requests through AMFI's own
www.amfiindia.com/gateway/ reverse proxy work fine via plain curl/httpx,
confirmed repeatedly. Use that path, not the CRISIL one directly.

Each scheme's `benchmark` field is the real, AMC-disclosed benchmark name
(e.g. "Nifty 100 TRI", "BSE 100 TRI") — not a guessed category mapping.
This is the source behind data_pipeline/orchestration/
benchmark_catalogue_sync.py's Scheme.benchmark_id backfill.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

GATEWAY_BASE_URL = "https://www.amfiindia.com/gateway/pollingsebi/api/amfi"
DEFAULT_TIMEOUT_SECONDS = 30.0

# investmentTypeList id, confirmed via the real filters response.
INVESTMENT_TYPE_EQUITY = 1

_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}


class FundPerformanceFetchError(RuntimeError):
    """Raised on any network failure, non-2xx response, or a response
    whose validationStatus isn't SUCCESS — never returns a partial or
    unvalidated result silently."""


@dataclass
class SubCategory:
    id: int
    name: str


@dataclass
class SchemePerformanceRow:
    scheme_name: str
    benchmark: str | None


def _post(path: str, payload: dict, timeout: float) -> dict:
    url = f"{GATEWAY_BASE_URL}/{path}"
    try:
        response = httpx.post(url, json=payload, headers=_HEADERS, timeout=timeout)
        response.raise_for_status()
    except httpx.TimeoutException as exc:
        raise FundPerformanceFetchError(f"Timed out fetching {url}") from exc
    except httpx.HTTPStatusError as exc:
        raise FundPerformanceFetchError(f"AMFI gateway returned HTTP {exc.response.status_code} for {url}") from exc
    except httpx.HTTPError as exc:
        raise FundPerformanceFetchError(f"Network error fetching {url}: {exc}") from exc

    try:
        body = response.json()
    except ValueError as exc:
        raise FundPerformanceFetchError(f"{url} returned non-JSON content") from exc

    if body.get("validationStatus") != "SUCCESS":
        raise FundPerformanceFetchError(f"{url} reported {body.get('validationStatus')}: {body.get('validationMsg')}")
    return body.get("data")


def fetch_subcategories(investment_type: int, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> list[SubCategory]:
    """Real sub-category list for one investmentTypeList id (e.g. the 14
    confirmed for Equity: Large Cap, Flexi Cap, Small Cap, Sectoral/
    Thematic, ...). Never guessed/hardcoded — fetched fresh each call,
    since AMFI could add a new sub-category at any time."""
    data = _post("getsubcategory", {"category": investment_type}, timeout)
    if not isinstance(data, list):
        raise FundPerformanceFetchError("getsubcategory returned an unexpected shape")
    return [SubCategory(id=row["id"], name=row["name"]) for row in data]


def fetch_scheme_performance(
    investment_type: int,
    sub_category_id: int,
    report_date: str,
    maturity_type: int = 1,  # 1 = Open Ended, confirmed; Close Ended funds aren't this platform's scope
    mfid: int = 0,  # confirmed: 0 = every AMC, not "no AMC"
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> list[SchemePerformanceRow]:
    """Every scheme (across every AMC) in one investment-type/sub-category
    combination, as of `report_date` (format "DD-Mon-YYYY", e.g.
    "19-Oct-2026") — confirmed real rows carry the scheme's own
    AMC-disclosed `benchmark` name directly, not a guess."""
    data = _post(
        "fundperformance",
        {
            "maturityType": maturity_type,
            "category": investment_type,
            "subCategory": sub_category_id,
            "mfid": mfid,
            "reportDate": report_date,
        },
        timeout,
    )
    if not isinstance(data, list):
        raise FundPerformanceFetchError("fundperformance returned an unexpected shape")
    return [SchemePerformanceRow(scheme_name=row["schemeName"], benchmark=row.get("benchmark")) for row in data]
