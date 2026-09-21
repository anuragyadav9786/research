"""Provider abstraction for benchmark (index) price history.

Mirrors the shape of data_pipeline/sources/amfi and .../mfapi (a small
client module per real source), but generalized behind one interface
(BenchmarkProvider) so the orchestration layer (lazy_benchmark_backfill.py)
and the research engine never need to know which provider actually served
a given benchmark's data — see Section 23's "research calculation
contract" principle, applied one layer down to data fetching itself.

Only NSEProvider (nse.py) is implemented, and only for TRI-family indices
that are the actual data class mutual fund scheme benchmarks use. BSE,
CRISIL and MSCI are registered as recognized `provider` values on the
Benchmark model (Section 5's provider abstraction) but have no working
client here — see registry.py's docstring for why, and
docs/data-sources.md for the standing "licensing/availability to confirm"
note this satisfies rather than overrides.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date


class BenchmarkProviderError(RuntimeError):
    """Raised when a provider cannot return benchmark data for a request —
    network failure, unknown symbol, malformed response, or (for a
    registered-but-unimplemented provider) simply "not available". Callers
    (lazy_benchmark_backfill.py) always catch this and degrade gracefully;
    it must never propagate into a request that renders a page.
    """


@dataclass
class BenchmarkPricePoint:
    price_date: date
    value: float


class BenchmarkProvider(ABC):
    """One external (or internal) source of benchmark index price history.

    A provider fetches RAW points for a symbol/date range — validation
    (data_pipeline/validation/benchmark_validation.py) and persistence
    (data_pipeline/storage/database_writer.py) happen one layer up, same
    separation NAV ingestion already uses between client/parser and
    validation/storage.
    """

    #: The Benchmark.provider value this class serves, e.g. "NSE".
    name: str

    @abstractmethod
    def fetch_range(self, symbol: str, start: date, end: date) -> list[BenchmarkPricePoint]:
        """Return this symbol's price points for [start, end] (inclusive).

        Raises BenchmarkProviderError on any failure — network, timeout,
        malformed response, or unknown symbol. Never returns a partial
        result silently; either the range was fetched or the error says
        why not, matching every other client in this pipeline.
        """
        raise NotImplementedError
