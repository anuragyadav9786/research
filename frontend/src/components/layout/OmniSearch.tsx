"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Search } from "lucide-react";

import { listFunds } from "@/lib/api";
import { FUND_CATEGORIES } from "@/lib/constants";
import type { FundSummary } from "@/types/fund";

interface CompareShortcut {
  kind: "compare";
  fundA: FundSummary;
  fundB: FundSummary;
}

interface CategoryShortcut {
  kind: "category";
  category: string;
}

type Shortcut = CompareShortcut | CategoryShortcut;

/** "PPFAS vs Quant" -> resolves each side to its best-matching fund via the
 * same fuzzy search every result row uses, so this never needs its own
 * matching logic or a second endpoint. Requires both sides to resolve —
 * a partial match (e.g. only "PPFAS" exists) falls through to the plain
 * fund-search results instead of showing a broken comparison link. */
async function resolveCompareShortcut(query: string): Promise<CompareShortcut | null> {
  const vsIndex = query.toLowerCase().indexOf(" vs ");
  if (vsIndex === -1) return null;
  const termA = query.slice(0, vsIndex).trim();
  const termB = query.slice(vsIndex + 4).trim();
  if (!termA || !termB) return null;

  const [resultsA, resultsB] = await Promise.all([
    listFunds({ search: termA, limit: 1 }).catch(() => null),
    listFunds({ search: termB, limit: 1 }).catch(() => null),
  ]);
  const fundA = resultsA?.items[0];
  const fundB = resultsB?.items[0];
  if (!fundA || !fundB) return null;
  return { kind: "compare", fundA, fundB };
}

function resolveCategoryShortcut(query: string): CategoryShortcut | null {
  const match = FUND_CATEGORIES.find((c) => c.toLowerCase() === query.trim().toLowerCase());
  return match ? { kind: "category", category: match } : null;
}

/** Global fund search, opened with Cmd/Ctrl+K from anywhere in the app.
 * Reuses the same fuzzy /api/funds search every other search box on this
 * site already calls — no separate search backend. Also resolves two
 * shortcuts above the plain fund results: "X vs Y" jumps straight to a
 * head-to-head compare, and an exact category name jumps to that filtered
 * list — both are just router.push()es to routes/params that already
 * exist (research/compare's ?a=&b=, /research's ?category=). */
export function OmniSearch() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<FundSummary[]>([]);
  const [shortcut, setShortcut] = useState<Shortcut | null>(null);
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
      setShortcut(null);
      setActiveIndex(0);
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  useEffect(() => {
    if (!open || query.trim().length === 0) {
      setResults([]);
      setShortcut(null);
      return;
    }
    let cancelled = false;
    setLoading(true);

    const categoryMatch = resolveCategoryShortcut(query);
    if (categoryMatch) {
      setShortcut(categoryMatch);
      setResults([]);
      setLoading(false);
      return;
    }

    const handle = setTimeout(() => {
      resolveCompareShortcut(query).then((compareMatch) => {
        if (cancelled) return;
        if (compareMatch) {
          setShortcut(compareMatch);
          setResults([]);
          setLoading(false);
          return;
        }
        setShortcut(null);
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
      });
    }, 200);
    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
  }, [query, open]);

  function goToFund(fund: FundSummary) {
    setOpen(false);
    router.push(`/research/${fund.id}`);
  }

  function goToShortcut(s: Shortcut) {
    setOpen(false);
    if (s.kind === "compare") {
      router.push(`/research/compare?a=${s.fundA.id}&b=${s.fundB.id}`);
    } else {
      router.push(`/research?category=${encodeURIComponent(s.category)}`);
    }
  }

  function onInputKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (shortcut) {
      if (e.key === "Enter") goToShortcut(shortcut);
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, Math.max(results.length - 1, 0)));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" && results[activeIndex]) {
      goToFund(results[activeIndex]);
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="flex items-center gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-2)]/60 px-2.5 py-1.5 sm:px-3 text-sm text-white/60 hover:border-[var(--border-hover)] hover:text-white/90 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--canvas)]"
      >
        <Search aria-hidden="true" className="h-3.5 w-3.5 flex-shrink-0" />
        {/* Always in the accessible tree (just visually hidden below sm:) so
         * the button's accessible name always matches its visible label —
         * an aria-label here previously fell out of sync with what desktop
         * users could actually see ("Search funds…" plus a "⌘K" hint),
         * which axe flags as a name/label mismatch. */}
        <span className="sr-only sm:not-sr-only sm:inline">Search funds…</span>
        <kbd
          aria-hidden="true"
          className="hidden sm:inline-flex items-center rounded border border-[var(--border-subtle)] bg-[var(--surface-1)] px-1.5 py-0.5 text-[10px] font-mono text-white/50"
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
            className="w-full max-w-xl rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-2 border-b border-[var(--border-subtle)] px-4 py-3">
              <Search className="h-4 w-4 text-white/50 flex-shrink-0" />
              <input
                id="omni-search-input"
                ref={inputRef}
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setActiveIndex(0);
                }}
                onKeyDown={onInputKeyDown}
                placeholder="Search funds, or try &ldquo;PPFAS vs Quant&rdquo;, &ldquo;Flexi Cap&rdquo;…"
                className="flex-1 bg-transparent text-sm text-white placeholder:text-white/40 focus:outline-none"
              />
              <kbd className="rounded border border-[var(--border-subtle)] px-1.5 py-0.5 text-[10px] font-mono text-white/50">
                Esc
              </kbd>
            </div>
            <div className="max-h-80 overflow-y-auto py-2">
              {loading && <p className="px-4 py-3 text-sm text-white/50">Searching…</p>}

              {!loading && shortcut?.kind === "compare" && (
                <button
                  type="button"
                  onClick={() => goToShortcut(shortcut)}
                  className="flex w-full flex-col items-start gap-0.5 px-4 py-2.5 text-left bg-blue-500/10 focus-visible:outline-none focus-visible:bg-blue-500/15"
                >
                  <span className="text-sm font-medium text-white">
                    Compare {shortcut.fundA.scheme_name} vs {shortcut.fundB.scheme_name} →
                  </span>
                  <span className="text-xs text-white/50">Head-to-head comparison</span>
                </button>
              )}

              {!loading && shortcut?.kind === "category" && (
                <button
                  type="button"
                  onClick={() => goToShortcut(shortcut)}
                  className="flex w-full flex-col items-start gap-0.5 px-4 py-2.5 text-left bg-blue-500/10 focus-visible:outline-none focus-visible:bg-blue-500/15"
                >
                  <span className="text-sm font-medium text-white">Browse {shortcut.category} funds →</span>
                  <span className="text-xs text-white/50">Category filter</span>
                </button>
              )}

              {!loading && !shortcut && query.trim().length > 0 && results.length === 0 && (
                <p className="px-4 py-3 text-sm text-white/50">No funds found for &ldquo;{query}&rdquo;.</p>
              )}
              {!loading &&
                !shortcut &&
                results.map((fund, i) => (
                  <button
                    key={fund.id}
                    type="button"
                    onClick={() => goToFund(fund)}
                    onMouseEnter={() => setActiveIndex(i)}
                    className={`flex w-full flex-col items-start px-4 py-2 text-left focus-visible:outline-none focus-visible:bg-[var(--surface-2)] ${
                      i === activeIndex ? "bg-[var(--surface-2)]" : ""
                    }`}
                  >
                    <span className="text-sm text-white">{fund.scheme_name}</span>
                    <span className="text-xs text-white/50">
                      {fund.amc_name} · {fund.category}
                    </span>
                  </button>
                ))}
              {!loading && !shortcut && query.trim().length === 0 && (
                <p className="px-4 py-3 text-sm text-white/50">Start typing to search funds…</p>
              )}
            </div>
            <div className="flex items-center justify-end gap-1 border-t border-[var(--border-subtle)] px-4 py-2 text-[11px] text-white/50">
              <span>Press</span>
              <kbd className="rounded border border-[var(--border-subtle)] px-1 py-0.5 font-mono">Enter ↵</kbd>
              <span>to open</span>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
