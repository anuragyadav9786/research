"""Return correlation between two funds (part of Section 11's Overlap
Engine: holdings can look different while returns move together, or vice
versa — correlation is the return-based complement to weighted overlap)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def return_correlation(returns_a: pd.Series, returns_b: pd.Series) -> float | None:
    """Pearson correlation coefficient between two daily-return series.

    Formula: standard Pearson correlation (numpy's `corrcoef`), computed
    only over dates present in both series (inner join) — mismatched
    trading calendars are aligned first, never force-filled.

    Interpretation: +1 = move in lockstep; 0 = no linear relationship;
    -1 = move in exact opposition. Two funds can have high correlation
    with low holdings overlap (both quietly track the market via different
    stocks) or the reverse (concentrated bets that happen to diverge) —
    report alongside `weighted_overlap_pct`, not as a substitute for it.

    Limitations: linear correlation only; requires at least 2 aligned
    observations and non-zero variance in both series (returns None,
    never a fabricated correlation, when either is degenerate — e.g. a
    fund with a single NAV data point, or a constant NAV).
    """
    aligned = pd.concat([returns_a.rename("a"), returns_b.rename("b")], axis=1).dropna()
    if len(aligned) < 2:
        return None
    if aligned["a"].std(ddof=1) == 0 or aligned["b"].std(ddof=1) == 0:
        return None
    matrix = np.corrcoef(aligned["a"], aligned["b"])
    return float(matrix[0, 1])
