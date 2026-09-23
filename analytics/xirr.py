"""Money-weighted (XIRR) return on an irregular sequence of cash flows.

Solves NPV(r) = Σ CF_i / (1+r)^((date_i - date_0)/365) = 0 for r, via
bisection over a wide, sane bracket rather than Newton-Raphson — no
derivative to get wrong, and bisection is guaranteed to converge given a
bracket where NPV changes sign, which every realistic investment cash-
flow sequence (money out, then money back) does. If NPV doesn't change
sign anywhere in the bracket, this returns None rather than guessing —
same "never fabricate a number" convention as the rest of this codebase.

Pure and deterministic, same as every other module here: no network
access, no randomness (Rule 4 in the project brief).
"""
from __future__ import annotations

from datetime import date

_LOWER_BOUND = -0.999999  # -99.9999% annualized — the floor before (1+r) hits zero
_UPPER_BOUND = 10.0  # +1000% annualized — comfortably above any realistic mutual fund return
_MAX_ITERATIONS = 200
_NPV_TOLERANCE = 1e-6
_BRACKET_TOLERANCE = 1e-9


def xirr(cash_flows: list[tuple[date, float]]) -> float | None:
    """`cash_flows`: (date, amount) pairs, positive = money received by
    the investor, negative = money paid out by the investor. Needs at
    least one of each sign — otherwise there's no rate of return to
    solve for (e.g. an all-outflow or all-inflow sequence), and this
    returns None. Result is a decimal rate (0.148 = 14.8% annualized),
    not a percentage.
    """
    if len(cash_flows) < 2:
        return None
    if not any(cf > 0 for _, cf in cash_flows) or not any(cf < 0 for _, cf in cash_flows):
        return None

    t0 = min(d for d, _ in cash_flows)

    def npv(rate: float) -> float:
        return sum(cf / (1.0 + rate) ** ((d - t0).days / 365.0) for d, cf in cash_flows)

    lo, hi = _LOWER_BOUND, _UPPER_BOUND
    npv_lo, npv_hi = npv(lo), npv(hi)
    if abs(npv_lo) < _NPV_TOLERANCE:
        return round(lo, 6)
    if abs(npv_hi) < _NPV_TOLERANCE:
        return round(hi, 6)
    if (npv_lo > 0) == (npv_hi > 0):
        return None  # no sign change across the bracket: no solution in a realistic range

    for _ in range(_MAX_ITERATIONS):
        mid = (lo + hi) / 2
        npv_mid = npv(mid)
        if abs(npv_mid) < _NPV_TOLERANCE or (hi - lo) < _BRACKET_TOLERANCE:
            return round(mid, 6)
        if (npv_mid > 0) == (npv_lo > 0):
            lo, npv_lo = mid, npv_mid
        else:
            hi, npv_hi = mid, npv_mid
    return round((lo + hi) / 2, 6)
