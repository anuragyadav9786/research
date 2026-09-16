import Link from "next/link";

const FOOTER_LINKS = [
  { href: "/research", label: "Research" },
  { href: "/research/compare", label: "Compare" },
  { href: "/portfolio", label: "Portfolio" },
  { href: "/market", label: "Market Pulse" },
] as const;

const LINK_CLASS =
  "hover:text-slate-300 transition-colors rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950";

/** Shared footer, rendered once from the root layout so every page gets it
 * without having to opt in individually — previously there was no footer
 * anywhere in the app; every page just ended after its last section. */
export function SiteFooter() {
  return (
    <footer className="border-t border-slate-800 bg-slate-950 px-8 py-8 text-slate-500">
      <div className="mx-auto flex max-w-5xl flex-col items-start justify-between gap-4 text-xs sm:flex-row sm:items-center">
        <p className="max-w-md">
          Every number shown here is either real, ingested market data or explicitly
          labelled sample data — never presented as if it were one thing.
        </p>
        <nav className="flex flex-wrap gap-x-5 gap-y-2">
          {FOOTER_LINKS.map((link) => (
            <Link key={link.href} href={link.href} className={LINK_CLASS}>
              {link.label}
            </Link>
          ))}
        </nav>
      </div>
      <p className="mx-auto mt-4 max-w-5xl text-[11px] text-slate-600">
        ThinkFin is a research tool, not investment advice.
      </p>
    </footer>
  );
}
