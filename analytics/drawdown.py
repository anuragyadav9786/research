"""Maximum drawdown and recovery-time calculations."""
from __future__ import annotations

import pandas as pd


def drawdown_series(nav: pd.Series) -> pd.Series:
    """Drawdown at every point in time relative to the running peak so far.

    Formula: nav / running_max(nav) - 1  (always <= 0)
    """
    nav = nav.sort_index()
    running_max = nav.cummax()
    return nav / running_max - 1.0


def max_drawdown(nav: pd.Series) -> dict:
    """Worst peak-to-trough decline in the series, with dates and recovery.

    Definition: the largest percentage drop from any historical peak to a
    subsequent trough, before a new peak is reached.

    Methodology:
      1. dd = drawdown_series(nav)
      2. trough_date = date of dd.min()
      3. peak_date = date of the running maximum NAV at/just before the
         trough (i.e. the peak this specific drawdown fell from)
      4. recovery_date = first date after the trough where nav >= peak NAV
         (None if the series ends before recovery — reported explicitly as
         "not yet recovered as of last available data", never guessed)
      5. recovery_duration_days = (recovery_date - trough_date).days

    Limitations: identifies exactly one (the worst) drawdown episode: a
    fund with several large, distinct drawdowns needs `all_drawdowns` (not
    yet implemented) to see all of them, not just the deepest.
    """
    nav = nav.sort_index()
    if len(nav) < 2:
        raise ValueError("need at least 2 NAV observations")

    dd = drawdown_series(nav)
    trough_date = dd.idxmin()
    max_dd_pct = float(dd.loc[trough_date])

    nav_up_to_trough = nav.loc[:trough_date]
    peak_date = nav_up_to_trough.idxmax()
    peak_nav = float(nav_up_to_trough.loc[peak_date])

    post_trough = nav.loc[trough_date:]
    recovered = post_trough[post_trough >= peak_nav]
    recovery_date = recovered.index[0] if not recovered.empty else None
    recovery_duration_days = (
        (recovery_date - trough_date).days if recovery_date is not None else None
    )

    return {
        "max_drawdown_pct": max_dd_pct,
        "peak_date": peak_date,
        "peak_nav": peak_nav,
        "trough_date": trough_date,
        "trough_nav": float(nav.loc[trough_date]),
        "recovery_date": recovery_date,
        "recovery_duration_days": recovery_duration_days,
        "recovered": recovery_date is not None,
    }


def _build_episode(nav: pd.Series, dd: pd.Series, peak_date, span_end_date, recovery_date) -> dict:
    span = dd.loc[peak_date:span_end_date]
    trough_date = span.idxmin()
    recovery_duration_days = (recovery_date - trough_date).days if recovery_date is not None else None
    return {
        "max_drawdown_pct": float(dd.loc[trough_date]),
        "peak_date": peak_date,
        "peak_nav": float(nav.loc[peak_date]),
        "trough_date": trough_date,
        "trough_nav": float(nav.loc[trough_date]),
        "recovery_date": recovery_date,
        "recovery_duration_days": recovery_duration_days,
        "recovered": recovery_date is not None,
    }


def drawdown_episodes(nav: pd.Series, min_magnitude_pct: float = 1.0) -> list[dict]:
    """Every distinct peak-to-trough episode in the series, most severe
    first — the multi-episode counterpart to max_drawdown(), which only
    ever returns the single worst one. Each episode dict has the exact
    same shape max_drawdown() returns, and the first element of this
    list's output always matches max_drawdown()'s result for the same
    series.

    An episode runs from a running-peak date until NAV either recovers
    to that peak (recovery_date set) or the series ends while still
    underwater (recovery_date=None, recovered=False) — mirroring
    max_drawdown()'s own "never guessed" treatment of an unrecovered
    drawdown.

    `min_magnitude_pct`: episodes shallower than this (a positive
    percentage, e.g. 1.0 = 1%) are omitted as noise from ordinary
    day-to-day fluctuation rather than a materially distinct drawdown.
    """
    nav = nav.sort_index()
    if len(nav) < 2:
        raise ValueError("need at least 2 NAV observations")

    running_max = nav.cummax()
    dd = nav / running_max - 1.0
    dates = dd.index

    episodes: list[dict] = []
    in_drawdown = False
    peak_idx: int | None = None

    for i, current_date in enumerate(dates):
        underwater = dd.loc[current_date] < 0
        if underwater and not in_drawdown:
            in_drawdown = True
            peak_idx = i - 1  # always >=0: dd is 0 at the series' own first point
        elif not underwater and in_drawdown:
            episodes.append(_build_episode(nav, dd, dates[peak_idx], dates[i - 1], recovery_date=current_date))
            in_drawdown = False
            peak_idx = None

    if in_drawdown:
        episodes.append(_build_episode(nav, dd, dates[peak_idx], dates[-1], recovery_date=None))

    material = [e for e in episodes if abs(e["max_drawdown_pct"]) * 100 >= min_magnitude_pct]
    return sorted(material, key=lambda e: e["max_drawdown_pct"])
