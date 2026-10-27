"""Tier 2: AMCs whose real download link only appears after JavaScript
runs (a dynamic SPA page, a client-side PDF/file-viewer widget, or a
background data API only discoverable by watching real network traffic
in a loaded page) — needs a real or headless browser, not a plain GET.

Mirae Asset below is migrated from a previously confirmed adapter, built
by loading the real page in Playwright and inspecting its actual network
requests. Every other AMC in this tier is an explicit stub until the
same real investigation has been done for it — see
_UnconfirmedTier2Scraper's docstring. Fabricating a dropdown selector or
API shape for HDFC/SBI/ICICI Prudential/Kotak/Nippon without having
watched their real pages would silently produce an adapter that looks
complete but returns nothing (or the wrong file) every month.
"""
from __future__ import annotations

import datetime
import os
import re
from urllib.parse import urljoin

import httpx

from scrapers.base_scraper import BaseScraper, ValidationError

HEADLESS = os.environ.get("HEADLESS", "true").lower() != "false"


class MiraeAssetScraper(BaseScraper):
    """Mirae Asset — migrated from the previously confirmed
    `fetch_mirae_asset` adapter. Confirmed real: rather than scraping
    /downloads/portfolio's static HTML (which never contains the file
    link — the page draws it client-side through a PDF-viewer widget),
    this calls the same background data API that widget itself calls,
    found by loading the page in a real headless browser (Playwright)
    and inspecting its network requests.

    Implemented with `httpx` directly (not a live Playwright browser)
    because the real endpoint turned out to be a plain POST once its
    session-cookie requirement was understood — Playwright was the tool
    used to *discover* that shape, not something needed on every run.
    This still lives in the tier2 module (not tier1) because discovering
    it required a real browser in the first place, and because a future
    AMC in this tier genuinely needing a live browser session each run
    should follow the same investigate-with-Playwright-first approach.

    KNOWN LIMITATION (carried over unchanged): the endpoint returned
    only its 10 most-recent items in testing, with no pagination
    parameter found yet — can miss the current month's file for some of
    Mirae Asset's ~35-40 schemes if more than 10 published in the same
    batch. Each missed scheme is simply absent from the results, not its
    own logged failure (AMC_Directory tracks success/failure per AMC
    row, not per scheme within it). Also: multiple real files can come
    back for one AMC in a month (one per scheme) — fetch_portfolio
    returns the first one found and logs the rest, since
    BaseScraper.fetch_portfolio's contract is one path per AMC per
    month; a future revision to the contract would be needed to carry
    all of them through to Drive without that limitation.
    """

    short_code = "MIRAE"
    _base_url = "https://www.miraeassetmf.co.in"
    _title_period_re = re.compile(r"as on \d+\w*\s+([A-Za-z]+)\s+(\d{4})", re.IGNORECASE)

    def _parse_title_period(self, title: str) -> tuple[int, int] | None:
        """Extracts the (month, year) an item's Title actually covers,
        e.g. 'Portfolio Details as on 31st August 2026 for ...' ->
        (8, 2026). Deliberately not using the item's own PublishDate
        field — confirmed via a real response that PublishDate is when
        the AMC uploaded the file (per SEBI, up to ~10 days into the
        following month), not the period it covers."""
        match = self._title_period_re.search(title or "")
        if not match:
            return None
        month_name, year_str = match.groups()
        try:
            month_num = datetime.datetime.strptime(month_name, "%B").month
        except ValueError:
            return None
        return month_num, int(year_str)

    def fetch_portfolio(self, target_month: str, output_dir: str) -> str | None:
        year_str, month_num_str = target_month.split("-")
        year, month_num = int(year_str), int(month_num_str)

        headers = {
            "Referer": f"{self._base_url}/downloads/portfolio",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "X-Requested-With": "XMLHttpRequest",
        }

        try:
            with httpx.Client(headers=headers, timeout=30.0, follow_redirects=True) as client:
                # Real session state the data API depends on only exists
                # after actually visiting the portfolio page first — not
                # from any request body — so visit it first, in the same
                # client, to pick up its session cookies.
                client.get(f"{self._base_url}/downloads/portfolio")
                resp = client.post(f"{self._base_url}/AjaxService/GetDownloadsData", json={})
        except Exception as exc:
            print(f"  Mirae Asset: GetDownloadsData request FAILED {type(exc).__name__}: {exc}")
            return None

        if resp.status_code != 200:
            print(f"  Mirae Asset: GetDownloadsData -> HTTP {resp.status_code}")
            return None

        data = resp.json() or {}
        items = data.get("Data") or []
        print(f"  Mirae Asset: GetDownloadsData returned {len(items)} item(s)")

        for item in items:
            title = item.get("Title", "")
            relative_url = item.get("URL")
            period = self._parse_title_period(title)
            if not relative_url or not period or period != (month_num, year):
                continue

            file_url = urljoin(self._base_url, relative_url)
            try:
                file_resp = httpx.get(file_url, timeout=30.0, follow_redirects=True)
            except Exception as exc:
                print(f"  Mirae Asset: {file_url} -> FAILED {type(exc).__name__}: {exc}")
                continue
            if file_resp.status_code != 200:
                print(f"  Mirae Asset: {file_url} -> HTTP {file_resp.status_code}")
                continue

            try:
                return self.save_validated(file_resp.content, target_month, output_dir)
            except ValidationError as exc:
                print(f"  Mirae Asset: {file_url} -> downloaded but failed validation: {exc}")
                continue

        print(f"  Mirae Asset: no file matched {target_month} among {len(items)} returned item(s) — needs manual confirmation")
        return None


class _UnconfirmedTier2Scraper(BaseScraper):
    """An AMC whose dynamic disclosure page has not been individually
    investigated yet. Real implementation needs a Playwright session
    that loads `disclosure_page_url`, selects the target month/year
    (likely via dropdowns — the exact selectors are AMC-specific and
    unconfirmed), and either intercepts the resulting file download or
    discovers the background API the page itself calls (as Mirae
    Asset's adapter above does) — the same one-AMC-at-a-time real
    investigation already used for PPFAS and Mirae Asset.
    """

    disclosure_page_url: str

    def fetch_portfolio(self, target_month: str, output_dir: str) -> str | None:
        raise NotImplementedError(
            f"{self.short_code}: no confirmed page structure yet. Investigate "
            f"{self.disclosure_page_url} with a real Playwright session (dropdown selectors, "
            "intercepted download, or the background API it calls) before implementing this."
        )


class HDFCScraper(_UnconfirmedTier2Scraper):
    short_code = "HDFC"
    disclosure_page_url = "https://www.hdfcfund.com/statutory-disclosure/portfolio"


class SBIScraper(_UnconfirmedTier2Scraper):
    short_code = "SBI"
    disclosure_page_url = "https://www.sbimf.com/statutory-disclosures/portfolio-disclosure"


class ICICIPrudentialScraper(_UnconfirmedTier2Scraper):
    short_code = "ICICIPRU"
    disclosure_page_url = "https://www.icicipruamc.com/downloads/portfolio-disclosure"


class KotakScraper(_UnconfirmedTier2Scraper):
    short_code = "KOTAK"
    disclosure_page_url = "https://www.kotakmf.com/downloads/monthly-portfolio"


class NipponScraper(_UnconfirmedTier2Scraper):
    short_code = "NIPPON"
    disclosure_page_url = "https://mf.nipponindiaim.com/InvestorServices/DownloadsAndFactsheets/Pages/MonthlyPortfolio.aspx"


TIER2_SCRAPERS: dict[str, type[BaseScraper]] = {
    "MIRAE": MiraeAssetScraper,
    "HDFC": HDFCScraper,
    "SBI": SBIScraper,
    "ICICIPRU": ICICIPrudentialScraper,
    "KOTAK": KotakScraper,
    "NIPPON": NipponScraper,
}

__all__ = [
    "MiraeAssetScraper",
    "HDFCScraper",
    "SBIScraper",
    "ICICIPrudentialScraper",
    "KotakScraper",
    "NipponScraper",
    "TIER2_SCRAPERS",
    "HEADLESS",
]
