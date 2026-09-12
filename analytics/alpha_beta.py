"""Beta and Jensen's alpha versus a benchmark."""
from __future__ import annotations

import numpy as np
import pandas as pd

from analytics.risk import PERIODS_PER_YEAR


def beta(fund_returns: pd.Series, benchmark_returns: pd.Series) -> float:
    """Beta: sensitivity of fund returns to benchmark returns.

    Formula: Cov(fund, benchmark) / Var(benchmark)

    Both covariance and variance use the sample (ddof=1) convention via
    numpy's default `np.cov`, and are computed only over dates present in
    both series (inner join) — a fund and benchmark with mismatched
    trading calendars are aligned first, not force-filled.

    Interpretation: beta = 1 moves in line with the benchmark; > 1 is more
    volatile than the benchmark; < 1 is less volatile; negative beta (rare
    for a long-only equity fund) moves opposite to the benchmark.

    Limitations: a single-factor (market-only) beta — it does not separate
    out sector, size or style effects. Requires at least 2 aligned
    observations and non-zero benchmark variance.
    """
    aligned = pd.concat(
        [fund_returns.rename("fund"), benchmark_returns.rename("benchmark")], axis=1
    ).dropna()
    if len(aligned) < 2:
        raise ValueError("need at least 2 aligned return observations")
    covariance_matrix = np.cov(aligned["fund"], aligned["benchmark"], ddof=1)
    benchmark_variance = covariance_matrix[1, 1]
    if benchmark_variance == 0:
        raise ValueError("cannot compute beta: zero benchmark variance")
    return float(covariance_matrix[0, 1] / benchmark_variance)


def jensen_alpha(fund_annualized_return: float, benchmark_annualized_return: float,
                  risk_free_rate_annual: float, fund_beta: float) -> float:
    """Jensen's Alpha (annualized), given already-computed annualized returns and beta.

    Formula: fund_return - [risk_free + beta * (benchmark_return - risk_free)]

    This is CAPM-expected excess return subtracted from actual return: alpha
    is the portion of the fund's return that beta (market exposure) alone
    does not explain.

    Interpretation: positive alpha = outperformed what its market exposure
    alone would predict; negative = underperformed that expectation. This
    is NOT the same as "the manager added value" in isolation — see the
    Fund Manager Skill Engine (later phase) for a fuller decomposition and
    its documented confidence caveats.
    """
    expected_return = risk_free_rate_annual + fund_beta * (benchmark_annualized_return - risk_free_rate_annual)
    return fund_annualized_return - expected_return


def annualize_return(daily_returns: pd.Series, periods_per_year: int = PERIODS_PER_YEAR) -> float:
    """Convenience: geometric annualized return from a daily return series.

    Formula: (prod(1 + r) ** (periods_per_year / n)) - 1
    """
    n = len(daily_returns)
    if n == 0:
        raise ValueError("need at least 1 return observation")
    compounded = (1.0 + daily_returns).prod()
    return float(compounded ** (periods_per_year / n) - 1.0)
