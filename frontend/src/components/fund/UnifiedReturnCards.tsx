"use client";

import { useEffect, useState } from "react";

import { useInvestmentInputs } from "@/components/fund/InvestmentContext";
import { ApiError, getFundInvestmentValue } from "@/lib/api";
import { formatLakh, formatMonthYear, formatPct, formatRupees, signColorClass } from "@/lib/format";
import type { InvestmentValueResponse, Option, Plan, ReturnsResponse, ReturnWindow } from "@/types/fund";

const WINDOW_KEYS = ["1y", "3y", "5y", "7y", "10y"] as const;
const WINDOW_LABELS: Record<(typeof WINDOW_KEYS)[number], string> = {
  "1y": "1Y", "3y": "3Y", "5y": "5Y", "7y": "7Y", "10y": "10Y",
};
const PERIOD_NAMES: Record<(typeof WINDOW_KEYS)[number], string> = {
  "1y": "1-year", "3y": "3-year", "5y": "5-year", "7y": "7-year", "10y": "10-year",
};

// Matches InvestmentControls' own debounce — typing an amount fires one
// request after the user pauses, not one per keystroke.
const DEBOUNCE_MS = 500;

function unavailableHint(w: ReturnWindow): string {
  if (w.reason === "scheme_too_young" && w.earliest_nav_date) {
    return `No NAV history before ${formatMonthYear(w.earliest_nav_date)}`;
  }
  return "Insufficient NAV history";
}

function unavailableAriaLabel(key: (typeof WINDOW_KEYS)[number], w: ReturnWindow): string {
  return `${PERIOD_NAMES[key]} return not available. ${unavailableHint(w)}.`;
}

/** Unified 1Y/3Y/5Y/7Y/10Y return cards — each one both the CAGR percentage
 * (always available from `returns`, fetched server-side) and, once a
 * lumpsum/SIP amount is entered via InvestmentControls, what that
 * investment would be worth today over the same window. Replaces what
 * used to be two separate rows (a percentage-only card grid, and a
 * separate boxed rupee-value panel) with one card per window that shows
 * both, matching how an investor actually reads "what did/would this
 * return" — the amount first, the rate underneath it. */
export function UnifiedReturnCards({
  fundId,
  plan,
  option,
  returns,
}: {
  fundId: number;
  plan: Plan;
  option: Option;
  returns: ReturnsResponse;
}) {
  const { lumpsum, sipAmount, sipFrequency, hasLumpsum, hasSip } = useInvestmentInputs();
  const [investment, setInvestment] = useState<InvestmentValueResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!hasLumpsum && !hasSip) {
      setInvestment(null);
      setError(null);
      return;
    }
    setError(null);
    const timer = setTimeout(() => {
      getFundInvestmentValue(fundId, {
        plan,
        option,
        ...(hasLumpsum ? { lumpsum } : {}),
        ...(hasSip ? { sip_amount: sipAmount, sip_frequency: sipFrequency } : {}),
      })
        .then((result) => setInvestment(result))
        .catch((err) => setError(err instanceof ApiError ? err.message : "Could not calculate investment value."));
    }, DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [fundId, plan, option, hasLumpsum, lumpsum, hasSip, sipAmount, sipFrequency]);

  const showAmounts = hasLumpsum || hasSip;

  return (
    <div>
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        {WINDOW_KEYS.map((key) => {
          const w = returns.windows[key];
          const inv = investment?.windows[key];
          const investedAmount = inv ? (inv.lumpsum_invested ?? 0) + (inv.sip_invested ?? 0) : null;

          if (!w.available) {
            return (
              <div
                key={key}
                className="rounded-lg border border-slate-800 p-4"
                aria-label={unavailableAriaLabel(key, w)}
                role="group"
              >
                <div className="text-xs uppercase tracking-wide text-slate-500" aria-hidden>
                  {WINDOW_LABELS[key]}
                </div>
                <div className="text-lg font-semibold mt-1 text-slate-600" aria-hidden>
                  Not available
                </div>
                <div className="text-xs text-slate-500 mt-1" aria-hidden>
                  {unavailableHint(w)}
                </div>
              </div>
            );
          }

          const showValue = showAmounts && inv?.available && inv.total_value !== null;

          return (
            <div key={key} className="rounded-lg border border-slate-800 p-4">
              <div className="text-xs uppercase tracking-wide text-slate-500">{WINDOW_LABELS[key]}</div>

              {showValue ? (
                <>
                  <div className="text-lg font-semibold mt-1 text-slate-100">{formatRupees(inv!.total_value)}</div>
                  <div className="text-xs text-slate-500 mt-1">Inv: {formatLakh(investedAmount)}</div>
                  <div className="border-t border-slate-800 my-2" />
                  <div className={`text-sm ${signColorClass(w.cagr_pct)}`}>Ret: {formatPct(w.cagr_pct)}</div>
                </>
              ) : (
                <div className={`text-lg font-semibold mt-1 ${signColorClass(w.cagr_pct)}`}>{formatPct(w.cagr_pct)}</div>
              )}
            </div>
          );
        })}
      </div>
      {error && <p className="text-sm text-rose-400 mt-2">{error}</p>}
      {!showAmounts && (
        <p className="text-xs text-slate-600 mt-2">
          Enter a lumpsum and/or SIP amount above to see what that investment would be worth today over each period.
        </p>
      )}
    </div>
  );
}
