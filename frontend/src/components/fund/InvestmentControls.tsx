"use client";

import { useInvestmentInputs } from "@/components/fund/InvestmentContext";
import type { SipFrequency } from "@/types/fund";

const SIP_FREQUENCY_OPTIONS: { value: SipFrequency; label: string }[] = [
  { value: "daily", label: "Daily" },
  { value: "weekly", label: "Weekly" },
  { value: "monthly", label: "Monthly" },
];

/** Compact lumpsum/SIP amount + frequency inputs for the page header —
 * feeds the unified return cards further down the page via
 * InvestmentContext. Both lumpsum and SIP can be filled at once (their
 * values combine in each return card), not an either/or toggle. */
export function InvestmentControls() {
  const { lumpsumInput, setLumpsumInput, sipInput, setSipInput, sipFrequency, setSipFrequency, hasSip } =
    useInvestmentInputs();

  const inputClass =
    "w-24 rounded-md border border-slate-800 bg-slate-900 px-2 py-1 text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-slate-600";

  return (
    <div className="flex flex-wrap items-center gap-2 text-sm text-slate-500 sm:border-l sm:border-slate-800 sm:pl-4">
      <span className="text-xs uppercase tracking-wide text-slate-500">Invest</span>
      <label className="flex items-center gap-1">
        Lump
        <input
          type="number"
          min="0"
          inputMode="decimal"
          placeholder="₹"
          value={lumpsumInput}
          onChange={(e) => setLumpsumInput(e.target.value)}
          className={inputClass}
          aria-label="Lumpsum investment amount"
        />
      </label>
      <label className="flex items-center gap-1">
        SIP
        <input
          type="number"
          min="0"
          inputMode="decimal"
          placeholder="₹"
          value={sipInput}
          onChange={(e) => setSipInput(e.target.value)}
          className={inputClass}
          aria-label="SIP installment amount"
        />
      </label>
      <select
        value={sipFrequency}
        onChange={(e) => setSipFrequency(e.target.value as SipFrequency)}
        disabled={!hasSip}
        className="rounded-md border border-slate-800 bg-slate-900 px-2 py-1 text-sm text-slate-300 focus:outline-none focus:border-slate-600 disabled:opacity-50"
        aria-label="SIP frequency"
      >
        {SIP_FREQUENCY_OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}
