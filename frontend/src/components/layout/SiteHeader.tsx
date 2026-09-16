import Link from "next/link";

import { OmniSearch } from "./OmniSearch";

const NAV_ITEMS = [
  { key: "dashboard", label: "Dashboard", href: "/" },
  { key: "research", label: "Research", href: "/research" },
  { key: "compare", label: "Compare", href: "/research/compare" },
  { key: "portfolio", label: "Portfolio", href: "/portfolio" },
  { key: "market", label: "Market Pulse", href: "/market" },
] as const;

export type SiteHeaderActive = (typeof NAV_ITEMS)[number]["key"];

/** Shared header used by every page — previously each page hand-duplicated
 * this block (and drifted: some had all 5 links, some had 4, only the
 * homepage still listed the never-built Reports/Admin). One component now,
 * used everywhere, plus the Cmd+K search this platform didn't have before. */
const FOCUS_RING =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950";

export function SiteHeader({ active }: { active?: SiteHeaderActive }) {
  return (
    <header className="border-b border-slate-800 px-8 py-4 flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
      <Link href="/" className={`text-lg font-semibold tracking-tight text-slate-100 rounded-sm ${FOCUS_RING}`}>
        ThinkFin
      </Link>
      <nav className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
        {NAV_ITEMS.map((item) => (
          <Link
            key={item.key}
            href={item.href}
            className={`border-b-2 pb-1 transition-colors rounded-sm ${FOCUS_RING} ${
              item.key === active
                ? "text-slate-100 font-medium border-indigo-500"
                : "text-slate-500 hover:text-slate-100 border-transparent"
            }`}
          >
            {item.label}
          </Link>
        ))}
      </nav>
      <OmniSearch />
    </header>
  );
}
