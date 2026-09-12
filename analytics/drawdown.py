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
