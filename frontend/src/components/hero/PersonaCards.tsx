import Link from "next/link";
import { Boxes, Flame, ShieldCheck, TrendingUp, type LucideIcon } from "lucide-react";

import { PERSONAS } from "@/lib/constants";

const PERSONA_ICONS: Record<string, LucideIcon> = {
  "capital-preservation": ShieldCheck,
  "consistent-compounders": TrendingUp,
  "aggressive-horizon": Flame,
  "check-overlap": Boxes,
};

function hrefFor(persona: (typeof PERSONAS)[number]): string {
  if (persona.href) return persona.href;
  const category = persona.categories!.join(",");
  return `/research?category=${encodeURIComponent(category)}&persona=${persona.id}`;
}

/** Four quick-start entry points below the hero, each a real filter this
 * platform can already back (AMFI category, or the existing /portfolio
 * overlap flow) rather than a generic "browse everything" search box —
 * see PERSONAS in lib/constants.ts for why category (not a per-fund
 * downside-capture threshold) is the honest filter to build this on
 * today. */
export function PersonaCards() {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
      {PERSONAS.map((persona) => {
        const Icon = PERSONA_ICONS[persona.id];
        return (
          <Link
            key={persona.id}
            href={hrefFor(persona)}
            className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] hover:border-[var(--border-hover)] hover:-translate-y-0.5 hover:shadow-lg hover:shadow-black/40 transition-all p-5 space-y-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--canvas)]"
          >
            <Icon aria-hidden="true" className="h-5 w-5 text-blue-500" />
            <h3 className="text-sm font-semibold text-white">{persona.label}</h3>
            <p className="text-sm text-white/50">{persona.description}</p>
          </Link>
        );
      })}
    </div>
  );
}
