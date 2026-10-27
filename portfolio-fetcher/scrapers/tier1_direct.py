"""Tier 1: AMCs whose portfolio file is reachable via a plain HTTP
GET/POST — a direct or predictable static link, no JavaScript-rendered
page needed. Each class below is either migrated from a real, previously
confirmed adapter (PPFAS), or an explicit stub for an AMC that has not
yet been individually investigated — see each class's own docstring.

Never guess a URL pattern or CSS selector for an AMC this module hasn't
actually confirmed against a real response, the same discipline every
other data source in this project's wider codebase follows (see e.g.
data_pipeline/sources/*'s module docstrings) — a fabricated adapter that
silently returns nothing (or worse, the wrong file) is harder to catch
than an honest NotImplementedError.
"""
from __future__ import annotations

import datetime

import httpx

from scrapers.base_scraper import BaseScraper, ValidationError

# bs4 is a requirements.txt dependency for this module's future
# confirmed adapters (an AMC whose real link sits in static HTML rather
# than a predictable URL pattern or a JSON API) — imported here only
# once a specific scraper actually needs it, not speculatively.


class PPFASScraper(BaseScraper):
    """PPFAS (Parag Parikh) — migrated from the previously confirmed
    `fetch_ppfas` adapter. Confirmed real: a consolidated workbook, one
    sheet per scheme, with genuine holdings rows.

    KNOWN LIMITATION (carried over unchanged): the disclosure page only
    reveals the current month's real download link via client-side
    JavaScript — a plain GET can't see it, so this guesses the URL from
    PPFAS's known filename pattern instead of discovering it for real.
    It can fail some months (a market holiday shifting the "as on" date,
    or PPFAS changing the pattern) — that's a real None return (logged
    upstream as NOT_FOUND), not a bug to silently paper over. Moving
    this to tier2 (Playwright) would resolve it properly; not done here
    to keep this adapter's dependencies minimal since it already works
    most months as-is.
    """

    short_code = "PPFAS"

    def fetch_portfolio(self, target_month: str, output_dir: str) -> str | None:
        year_str, month_num_str = target_month.split("-")
        year, month_num = int(year_str), int(month_num_str)
        next_month = datetime.date(year, month_num, 28) + datetime.timedelta(days=4)
        last_day = next_month - datetime.timedelta(days=next_month.day)

        # Try the exact last calendar day, then a few days back, in case
        # the real "as on" date was an earlier business day.
        candidates = [last_day - datetime.timedelta(days=offset) for offset in range(0, 4)]

        for day in candidates:
            url = (
                f"https://amc.ppfas.com/downloads/portfolio-disclosure/{year}/"
                f"PPFAS_Monthly_Portfolio_Report_{day.strftime('%B')}_{day.day}_{year}.xls"
            )
            try:
                resp = httpx.get(url, timeout=30.0, follow_redirects=True)
            except Exception as exc:
                print(f"  PPFAS: {url} -> FAILED {type(exc).__name__}: {exc}")
                continue
            if resp.status_code == 200:
                try:
                    return self.save_validated(resp.content, target_month, output_dir)
                except ValidationError as exc:
                    print(f"  PPFAS: {url} -> downloaded but failed validation: {exc}")
                    continue
            print(f"  PPFAS: {url} -> HTTP {resp.status_code}")

        print(f"  PPFAS: no file found for {target_month} after {len(candidates)} date guesses — needs manual confirmation")
        return None


class _UnconfirmedTier1Scraper(BaseScraper):
    """Shared NotImplementedError for an AMC whose real disclosure URL
    pattern has not been individually confirmed yet — the same one-AMC-
    at-a-time investigation PPFAS and Mirae Asset already went through
    (a read-only debug step that fetches the real page, as this
    project's own daily-nav-ingestion.yml already does for other AMCs:
    see its `debug_amc_disclosure_url` / `debug_ppfas_disclosure` steps)
    is needed before this can return real data instead of raising.
    """

    disclosure_page_url: str

    def fetch_portfolio(self, target_month: str, output_dir: str) -> str | None:
        raise NotImplementedError(
            f"{self.short_code}: no confirmed direct-link pattern yet. Investigate "
            f"{self.disclosure_page_url} for its real file-link shape (the same way PPFAS's "
            "and Mirae Asset's adapters were built) before implementing this."
        )


class DSPScraper(_UnconfirmedTier1Scraper):
    short_code = "DSP"
    disclosure_page_url = "https://www.dspim.com/statutory-disclosure/portfolio-disclosure"


class BandhanScraper(_UnconfirmedTier1Scraper):
    short_code = "BANDHAN"
    disclosure_page_url = "https://www.bandhanmutual.com/statutory-disclosure/portfolio"


class QuantScraper(_UnconfirmedTier1Scraper):
    short_code = "QUANT"
    disclosure_page_url = "https://www.quantmutual.com/downloads"


class WhiteOakScraper(_UnconfirmedTier1Scraper):
    short_code = "WHITEOAK"
    disclosure_page_url = "https://www.whiteoakamc.com/statutory-disclosures"


TIER1_SCRAPERS: dict[str, type[BaseScraper]] = {
    "PPFAS": PPFASScraper,
    "DSP": DSPScraper,
    "BANDHAN": BandhanScraper,
    "QUANT": QuantScraper,
    "WHITEOAK": WhiteOakScraper,
}

__all__ = [
    "PPFASScraper",
    "DSPScraper",
    "BandhanScraper",
    "QuantScraper",
    "WhiteOakScraper",
    "TIER1_SCRAPERS",
]
