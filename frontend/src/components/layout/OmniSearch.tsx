"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { listFunds } from "@/lib/api";
import type { FundSummary } from "@/types/fund";

/** Global fund search, opened with Cmd/Ctrl+K from anywhere in the app.
 * Reuses the same fuzzy /api/funds search every other search box on this
 * site already calls — no separate search backend. */
export function OmniSearch() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<FundSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      } else if (e.key === "Escape") {
        setOpen(false);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  useEffect(() => {
    if (open) {
      setQuery("");
      setResults([]);
      setActiveIndex(0);
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  useEffect(() => {
    if (!open || query.trim().length === 0) {
      setResults([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    const handle = setTimeout(() => {
      listFunds({ search: query, limit: 8 })
        .then((r) => {
          if (!cancelled) setResults(r.items);
        })
        .catch(() => {
          if (!cancelled) setResults([]);
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    }, 200);
    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
  }, [query, open]);

  function goTo(fund: FundSummary) {
    setOpen(false);
    router.push(`/research/${fund.id}`);
  }

  function onInputKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, Math.max(results.length - 1, 0)));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" && results[activeIndex]) {
      goTo(results[activeIndex]);
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="flex items-center gap-2 rounded-md border border-slate-800 bg-slate-900/60 px-2.5 py-1.5 sm:px-3 text-sm text-slate-400 hover:border-slate-700 hover:text-slate-200 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
      >
        <SearchIcon aria-hidden="true" className="h-3.5 w-3.5 flex-shrink-0" />
        {/* Always in the accessible tree (just visually hidden below sm:) so
         * the button's accessible name always matches its visible label —
         * an aria-label here previously fell out of sync with what desktop
         * users could actually see ("Search funds…" plus a "⌘K" hint),
         * which axe flags as a name/label mismatch. */}
        <span className="sr-only sm:not-sr-only sm:inline">Search funds…</span>
        <kbd
          aria-hidden="true"
          className="hidden sm:inline-flex items-center rounded border border-slate-700 bg-slate-800 px-1.5 py-0.5 text-[10px] font-mono text-slate-300"
        >
          ⌘K
        </kbd>
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 pt-24 px-4"
          onClick={() => setOpen(false)}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Search funds"
            className="w-full max-w-xl rounded-lg border border-slate-800 bg-slate-950 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-2 border-b border-slate-800 px-4 py-3">
              <SearchIcon className="h-4 w-4 text-slate-500 flex-shrink-0" />
              <input
                id="omni-search-input"
                ref={inputRef}
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setActiveIndex(0);
                }}
                onKeyDown={onInputKeyDown}
                placeholder="Search by fund name, AMC, or category…"
                className="flex-1 bg-transparent text-sm text-slate-100 placeholder:text-slate-600 focus:outline-none"
              />
              <kbd className="rounded border border-slate-700 px-1.5 py-0.5 text-[10px] font-mono text-slate-500">
                Esc
              </kbd>
            </div>
            <div className="max-h-80 overflow-y-auto py-2">
              {loading && <p className="px-4 py-3 text-sm text-slate-500">Searching…</p>}
              {!loading && query.trim().length > 0 && results.length === 0 && (
                <p className="px-4 py-3 text-sm text-slate-500">No funds found for &ldquo;{query}&rdquo;.</p>
              )}
              {!loading &&
                results.map((fund, i) => (
                  <button
                    key={fund.id}
                    type="button"
                    onClick={() => goTo(fund)}
                    onMouseEnter={() => setActiveIndex(i)}
                    className={`flex w-full flex-col items-start px-4 py-2 text-left focus-visible:outline-none focus-visible:bg-slate-900 ${
                      i === activeIndex ? "bg-slate-900" : ""
                    }`}
                  >
                    <span className="text-sm text-slate-100">{fund.scheme_name}</span>
                    <span className="text-xs text-slate-500">
                      {fund.amc_name} · {fund.category}
                    </span>
                  </button>
                ))}
              {!loading && query.trim().length === 0 && (
                <p className="px-4 py-3 text-sm text-slate-500">Start typing to search funds…</p>
              )}
            </div>
            <div className="flex items-center justify-end gap-1 border-t border-slate-800 px-4 py-2 text-[11px] text-slate-600">
              <span>Press</span>
              <kbd className="rounded border border-slate-700 px-1 py-0.5 font-mono">Enter ↵</kbd>
              <span>to open</span>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function SearchIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={className}>
      <circle cx="11" cy="11" r="7" />
      <path d="m21 21-4.35-4.35" />
    </svg>
  );
}
