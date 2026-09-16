"use client";

import { useState } from "react";
import Link from "next/link";

import type { SiteHeaderActive } from "./SiteHeader";

const FOCUS_RING =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950";

/** Hamburger + slide-down panel for the nav links, shown only below `sm:` —
 * the header's own nav switches to `hidden sm:flex` at that same breakpoint,
 * so exactly one of the two is ever visible. Without this, five nav links
 * wrapped onto a second line on a phone-width screen, eating vertical space
 * before any page content appeared. */
export function MobileNav({
  items,
  active,
}: {
  items: readonly { key: string; label: string; href: string }[];
  active?: SiteHeaderActive;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="sm:hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label={open ? "Close menu" : "Open menu"}
        aria-expanded={open}
        className={`flex h-8 w-8 items-center justify-center rounded-md border border-slate-800 text-slate-300 ${FOCUS_RING}`}
      >
        {open ? <CloseIcon className="h-4 w-4" /> : <MenuIcon className="h-4 w-4" />}
      </button>

      {open && (
        <nav className="absolute inset-x-0 top-full z-40 flex flex-col border-b border-slate-800 bg-slate-950 px-8 py-3 text-sm">
          {items.map((item) => (
            <Link
              key={item.key}
              href={item.href}
              onClick={() => setOpen(false)}
              className={`rounded-sm py-2.5 transition-colors ${FOCUS_RING} ${
                item.key === active ? "text-slate-100 font-medium" : "text-slate-400 hover:text-slate-100"
              }`}
            >
              {item.label}
            </Link>
          ))}
        </nav>
      )}
    </div>
  );
}

function MenuIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={className}>
      <path strokeLinecap="round" d="M4 6h16M4 12h16M4 18h16" />
    </svg>
  );
}

function CloseIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={className}>
      <path strokeLinecap="round" d="M6 6l12 12M18 6L6 18" />
    </svg>
  );
}
