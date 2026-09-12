"""HTTP client for AMFI's public NAVAll.txt bulk NAV file.

AMFI (Association of Mutual Funds in India) publishes the current NAV of
every registered scheme, updated once per business day, at a single
well-known URL. No API key or registration required — this is the
zero-budget-appropriate primary NAV source (Rule 5).

NOTE ON THIS SANDBOX: outbound HTTPS to amfiindia.com is blocked by this
development environment's network policy (confirmed via the agent proxy's
`/__agentproxy/status` diagnostics, which showed a 403 policy denial on
CONNECT to www.amfiindia.com:443). `fetch_navall` below has not been
exercised against the live endpoint in this session — only its error
handling has been unit-tested with a mocked transport. It must be run
against the real URL, from an environment with outbound internet access,
before Phase 3 is considered verified end-to-end.
"""
from __future__ import annotations

import httpx

NAVALL_URL = "https://www.amfiindia.com/spages/NAVAll.txt"
DEFAULT_TIMEOUT_SECONDS = 30.0


class NavFetchError(RuntimeError):
    """Raised when the NAVAll.txt file cannot be downloaded or is empty.

    Deliberately distinct from a generic exception so callers (the
    orchestration layer) can catch it specifically and log a clear
    ingestion-run failure reason, instead of a bare traceback.
    """


def fetch_navall(url: str = NAVALL_URL, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> str:
    """Download the raw NAVAll.txt content.

    Raises NavFetchError on any network failure, timeout, non-2xx response,
    or an empty body — never returns a partial/invalid result silently.
    """
    try:
        response = httpx.get(url, timeout=timeout, follow_redirects=True)
        response.raise_for_status()
    except httpx.TimeoutException as exc:
        raise NavFetchError(f"Timed out fetching {url}") from exc
    except httpx.HTTPStatusError as exc:
        raise NavFetchError(
            f"AMFI returned HTTP {exc.response.status_code} for {url}"
        ) from exc
    except httpx.HTTPError as exc:
        raise NavFetchError(f"Network error fetching {url}: {exc}") from exc

    text = response.text
    if not text or not text.strip():
        raise NavFetchError(f"{url} returned an empty response body")
    return text
