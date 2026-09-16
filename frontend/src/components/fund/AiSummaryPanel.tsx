"use client";

import { useState } from "react";

import { ApiError, getFundAiSummary } from "@/lib/api";
import type { Option, Plan } from "@/types/fund";
import type { AISummaryResponse } from "@/types/aiSummary";

/** On-demand, not auto-loaded: an LLM call has a real cost and this
 * project runs on a zero budget (Rule 5) — the user opts in per fund
 * rather than every page view triggering one. */
export function AiSummaryPanel({ fundId, plan, option }: { fundId: number; plan: Plan; option: Option }) {
  const [result, setResult] = useState<AISummaryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleGenerate() {
    setLoading(true);
    setError(null);
    try {
      const data = await getFundAiSummary(fundId, { plan, option });
      setResult(data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not generate a summary.");
    } finally {
      setLoading(false);
    }
  }

  if (!result && !error) {
    return (
      <button
        onClick={handleGenerate}
        disabled={loading}
        className="text-sm rounded-md border border-slate-700 bg-slate-800 px-4 py-2 hover:bg-slate-700 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
      >
        {loading ? "Generating…" : "Generate AI Summary"}
      </button>
    );
  }

  if (error) {
    return <p className="text-sm text-rose-400">{error}</p>;
  }

  if (!result!.available) {
    return (
      <div className="rounded-lg border border-slate-800 p-4">
        <p className="text-sm text-slate-500">{result!.reason}</p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-slate-800 p-4 space-y-3">
      <p className="text-sm text-slate-200 leading-relaxed">{result!.summary}</p>
      <p className="text-xs text-slate-600 border-t border-slate-900 pt-3">{result!.ai_disclaimer}</p>
    </div>
  );
}
