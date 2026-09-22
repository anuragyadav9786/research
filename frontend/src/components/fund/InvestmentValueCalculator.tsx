"use client";

import { useEffect, useState } from "react";

import { ApiError, getFundInvestmentValue } from "@/lib/api";
import { formatRupees } from "@/lib/format";
import type { InvestmentValueResponse, Option, Plan, SipFrequency } from "@/types/fund";

const WINDOW_KEYS = ["1y", "3y", "5y", "7y", "10y"] as const;
const WINDOW_LABELS: Record<(typeof WINDOW_KEYS)[number], string> = {
  "1y": "1Y", "3y": "3Y", "5y": "5Y", "7y": "7Y", "10y": "10Y",
};
const SIP_FREQUENCY_OPTIONS: { value: SipFrequency; label: string }[] = [
  { value: "daily", label: "Daily" },
  { value: "weekly", label: "Weekly" },
  { value: "monthly", label: "Monthly" },
];

// A number input fires on every keystroke — debounce so typing "100000"
// doesn't fire 6 requests, only the one after the user pauses.
const DEBOUNCE_MS = 500;

function unavailableHint(reason: string | null): string {
  if (reason === "scheme_too_young") return "Scheme too young for this window";
  if (reason === "no_nav_history") return "No NAV history";
  return "Insufficient NAV history";
}

export function InvestmentValueCalculator({ fundId, plan, option }: { fundId: number; plan: Plan; option: Option }) {
  const [lumpsumInput, setLumpsumInput] = useState("");
  const [sipInput, setSipInput] = useState("");
  const [sipFrequency, setSipFrequency] = useState<SipFrequency>("monthly");
  const [data, setData] = useState<InvestmentValueResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const lumpsum = Number(lumpsumInput);
  const sipAmount = Number(sipInput);
  const hasLumpsum = lumpsumInput.trim() !== "" && lumpsum > 0;
  const hasSip = sipInput.trim() !== "" && sipAmount > 0;

  useEffect(() => {
    if (!hasLumpsum && !hasSip) {
      setData(null);
      setError(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    const timer = setTimeout(() => {
      getFundInvestmentValue(fundId, {
        plan,
        option,
        ...(hasLumpsum ? { lumpsum } : {}),
        ...(hasSip ? { sip_amount: sipAmount, sip_frequency: sipFrequency } : {}),
      })
        .then((result) => setData(result))
        .catch((err) => setError(err instanceof ApiError ? err.message : "Could not calculate investment value."))
        .finally(() => setLoading(false));
    }, DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [fundId, plan, option, hasLumpsum, lumpsum, hasSip, sipAmount, sipFrequency]);

  const inputClass =
    "w-full rounded-md border border-slate-800 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-slate-600";

  return (
    <div className="mt-4 rounded-lg border border-slate-800 p-4">
      <h3 className="text-xs uppercase tracking-wide text-slate-500 mb-3">What would this be worth today?</h3>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <label className="text-xs text-slate-500">
          Lumpsum (₹)
          <input
            type="number"
            min="0"
            inputMode="decimal"
            placeholder="e.g. 100000"
            value={lumpsumInput}
            onChange={(e) => setLumpsumInput(e.target.value)}
            className={`${inputClass} mt-1`}
          />
        </label>
        <label className="text-xs text-slate-500">
          SIP amount (₹)
          <input
            type="number"
            min="0"
            inputMode="decimal"
            placeholder="e.g. 5000"
            value={sipInput}
            onChange={(e) => setSipInput(e.target.value)}
            className={`${inputClass} mt-1`}
          />
        </label>
        <label className="text-xs text-slate-500">
          SIP frequency
          <select
            value={sipFrequency}
            onChange={(e) => setSipFrequency(e.target.value as SipFrequency)}
            disabled={!hasSip}
            className={`${inputClass} mt-1 disabled:opacity-50`}
          >
            {SIP_FREQUENCY_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {!hasLumpsum && !hasSip && (
        <p className="text-xs text-slate-600 mt-3">
          Enter a lumpsum amount, a SIP amount, or both, to see what that investment would be worth today across each
          period.
        </p>
      )}

      {error && <p className="text-sm text-rose-400 mt-3">{error}</p>}

      {data && (hasLumpsum || hasSip) && (
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mt-4">
          {WINDOW_KEYS.map((key) => {
            const w = data.windows[key];
            const investedAmount = (w.lumpsum_invested ?? 0) + (w.sip_invested ?? 0);
            return (
              <div key={key} className="rounded-lg border border-slate-800 p-3">
                <div className="text-xs uppercase tracking-wide text-slate-500">{WINDOW_LABELS[key]}</div>
                {w.available && w.total_value !== null ? (
                  <>
                    <div className="text-base font-semibold mt-1 text-slate-100">{formatRupees(w.total_value)}</div>
                    <div className="text-xs text-slate-500 mt-1">invested {formatRupees(investedAmount)}</div>
                  </>
                ) : (
                  <>
                    <div className="text-sm text-slate-600 mt-1">Not available</div>
                    <div className="text-xs text-slate-600 mt-1">{unavailableHint(w.reason)}</div>
                  </>
                )}
              </div>
            );
          })}
        </div>
      )}
      {loading && <p className="text-xs text-slate-600 mt-2">Calculating…</p>}
    </div>
  );
}
