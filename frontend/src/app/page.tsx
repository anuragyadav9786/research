import Link from "next/link";

import { listFunds } from "@/lib/api";

const NAV = [
  { label: "Dashboard", href: "/" },
  { label: "Research", href: "/research" },
  { label: "Compare", href: "/research/compare" },
  { label: "Portfolio", href: "/portfolio" },
  { label: "Market Intelligence", href: "/market" },
  { label: "Reports", href: null },
  { label: "Admin", href: null }, // Data Status dashboard — Phase 3 automation follow-up
];

async function getBackendHealth() {
  const url = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  try {
    const res = await fetch(`${url}/api/health`, { cache: "no-store" });
    if (!res.ok) return { status: "unreachable" };
    return res.json();
  } catch {
    return { status: "unreachable" };
  }
}

export default async function Home() {
  const [health, funds] = await Promise.all([
    getBackendHealth(),
    listFunds().catch(() => []),
  ]);

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-100">
      <header className="border-b border-neutral-800 px-8 py-4 flex items-center justify-between">
        <span className="text-lg font-semibold tracking-tight">ThinkFin</span>
        <nav className="flex gap-6 text-sm text-neutral-400">
          {NAV.map((item) =>
            item.href ? (
              <Link key={item.label} href={item.href} className="hover:text-neutral-100">
                {item.label}
              </Link>
            ) : (
              <span key={item.label} className="text-neutral-700" title="Not built yet">
                {item.label}
              </span>
            ),
          )}
        </nav>
      </header>

      <main className="px-8 py-10 max-w-5xl mx-auto space-y-6">
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <p className="text-neutral-400 text-sm">
          Mutual Fund Decision Intelligence Platform.
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Link
            href="/research"
            className="rounded-lg border border-neutral-800 p-6 space-y-2 hover:border-neutral-700 transition-colors"
          >
            <h2 className="text-sm uppercase tracking-wide text-neutral-500">Funds Covered</h2>
            <p className="text-2xl font-semibold">{funds.length}</p>
            <p className="text-xs text-neutral-500">Browse Research →</p>
          </Link>

          <div className="rounded-lg border border-neutral-800 p-6 space-y-2">
            <h2 className="text-sm uppercase tracking-wide text-neutral-500">Backend Health</h2>
            <p className="font-mono text-sm">{JSON.stringify(health)}</p>
          </div>
        </div>
      </main>
    </div>
  );
}
