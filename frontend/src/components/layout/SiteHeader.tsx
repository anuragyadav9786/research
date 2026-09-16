import Image from "next/image";
import Link from "next/link";

import { MobileNav } from "./MobileNav";
import { OmniSearch } from "./OmniSearch";

const NAV_ITEMS = [
  { key: "research", label: "Research", href: "/research" },
  { key: "compare", label: "Compare", href: "/research/compare" },
  { key: "portfolio", label: "Portfolio", href: "/portfolio" },
  { key: "market", label: "Market Pulse", href: "/market" },
] as const;

export type SiteHeaderActive = (typeof NAV_ITEMS)[number]["key"];

/** Shared header used by every page — previously each page hand-duplicated
 * this block (and drifted: some had all 5 links, some had 4, only the
 * homepage still listed the never-built Reports/Admin). One component now,
 * used everywhere, plus the Cmd+K search this platform didn't have before.
 *
 * Nav is the Institutional Terminal brief's four named sections only — the
 * logo already routes home, so a separate "Dashboard" tab (the old fifth
 * item) was redundant with it. */
const FOCUS_RING =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--canvas)]";

export function SiteHeader({ active }: { active?: SiteHeaderActive }) {
  return (
    <header className="sticky top-0 z-40 border-b border-[var(--border-subtle)] bg-[var(--surface-1)]/80 px-8 py-4 flex items-center justify-between gap-x-6 gap-y-3 backdrop-blur-xl">
      <Link href="/" className={`flex items-center gap-2 rounded-sm ${FOCUS_RING}`}>
        <Image src="/icon/icon.png" alt="ThinkFin" width={32} height={32} className="h-8 w-8" priority />
        <span className="text-lg font-semibold tracking-tight text-white">ThinkFin</span>
      </Link>
      <nav className="hidden lg:flex flex-wrap gap-x-6 gap-y-1 text-sm">
        {NAV_ITEMS.map((item) => (
          <Link
            key={item.key}
            href={item.href}
            className={`border-b-2 border-transparent pb-1 transition-colors rounded-sm ${FOCUS_RING} ${
              item.key === active ? "text-white font-medium" : "text-white/60 hover:text-white"
            }`}
          >
            {item.label}
          </Link>
        ))}
      </nav>
      <div className="flex items-center gap-3">
        <OmniSearch />
        <MobileNav items={NAV_ITEMS} active={active} />
      </div>
    </header>
  );
}
