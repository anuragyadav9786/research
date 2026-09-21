"""Maps a Benchmark.provider string to a working BenchmarkProvider — the
one place that decides which providers are actually enabled.

BSE, CRISIL and MSCI are recognized provider names (a Benchmark row can
carry them, and the architecture is ready for them — Section 5) but have
no client implemented here: none of the three offers a confirmed, free,
key-less historical-data endpoint the way NSE's public index-history page
does, and this project's own rule is to mark such a benchmark unavailable
rather than build a fragile scrape or fabricate one (docs/data-sources.md
section 4). Add a real client under this package and register it here
once a legitimate source is confirmed for one of them.

NSE is enabled by default (Settings.benchmark_nse_provider_enabled) and
its response PARSING is now confirmed against a real captured response
(see nse.py's module docstring). It serves both price and TRI index
variants through one endpoint, keyed by which symbol is queried — so
getting the right series for a TRI benchmark depends on that benchmark's
`symbol` actually naming the TRI variant (e.g. "NIFTY 50 TRI"), not on
this registry.
"""
from __future__ import annotations

from app.core.config import get_settings
from data_pipeline.sources.benchmarks.base import BenchmarkProvider
from data_pipeline.sources.benchmarks.nse import NSEProvider

_UNIMPLEMENTED_PROVIDERS = frozenset({"BSE", "CRISIL", "MSCI"})


def get_provider(provider_name: str | None) -> BenchmarkProvider | None:
    """Returns a ready-to-use provider for `provider_name`, or None if no
    enabled provider handles it — a benchmark with no provider set, an
    unimplemented one (BSE/CRISIL/MSCI), or NSE while it's disabled all
    return None here, and the caller (lazy_benchmark_backfill.py) treats
    None the same way regardless of which of those it was: "can't fetch,
    fall back to cache or report unavailable" — never a crash, never a
    distinction the UI would need to make.
    """
    if not provider_name:
        return None
    if provider_name in _UNIMPLEMENTED_PROVIDERS:
        return None
    if provider_name == "NSE":
        if not get_settings().benchmark_nse_provider_enabled:
            return None
        return NSEProvider()
    return None
