"use client";

import { useState } from "react";
import Link from "next/link";
import { Menu, X } from "lucide-react";

import type { SiteHeaderActive } from "./SiteHeader";

const FOCUS_RING =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--canvas)]";

/** Hamburger + slide-down panel for the nav links, shown only below `lg:` —
 * the header's own nav switches to `hidden lg:flex` at that same breakpoint,
 * so exactly one of the two is ever visible. `lg:` (1024px), not `sm:`
 * (640px), because five nav links plus the logo and search box measurably
 * still wrap onto a second line at 640-768px — 1024px is the first width
 * that reliably fits everything on one line. */
export function MobileNav({
  items,
  active,
}: {
  items: readonly { key: string; label: string; href: string }[];
  active?: SiteHeaderActive;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="lg:hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label={open ? "Close menu" : "Open menu"}
        aria-expanded={open}
        className={`flex h-8 w-8 items-center justify-center rounded-md border border-[var(--border-subtle)] text-white/80 ${FOCUS_RING}`}
      >
        {open ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
      </button>

      {open && (
        <nav className="absolute inset-x-0 top-full z-40 flex flex-col border-b border-[var(--border-subtle)] bg-[var(--surface-1)] px-8 py-3 text-sm">
          {items.map((item) => (
            <Link
              key={item.key}
              href={item.href}
              onClick={() => setOpen(false)}
              className={`rounded-sm py-2.5 transition-colors ${FOCUS_RING} ${
                item.key === active ? "text-white font-medium" : "text-white/60 hover:text-white"
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
