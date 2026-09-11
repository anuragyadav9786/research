const NAV = [
  { label: "Dashboard", href: "/" },
  { label: "Research", href: "/research" },
  { label: "Portfolio", href: "/portfolio" },
  { label: "Market Intelligence", href: "/market" },
  { label: "Reports", href: "/reports" },
  { label: "Admin", href: "/admin" },
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
  const health = await getBackendHealth();

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-100">
      <header className="border-b border-neutral-800 px-8 py-4 flex items-center justify-between">
        <span className="text-lg font-semibold tracking-tight">ThinkFin</span>
        <nav className="flex gap-6 text-sm text-neutral-400">
          {NAV.map((item) => (
            <span key={item.href}>{item.label}</span>
          ))}
        </nav>
      </header>

      <main className="px-8 py-10 max-w-5xl mx-auto space-y-6">
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <p className="text-neutral-400 text-sm">
          Mutual Fund Decision Intelligence Platform — Phase 1 foundation shell.
        </p>

        <div className="rounded-lg border border-neutral-800 p-6 space-y-2">
          <h2 className="text-sm uppercase tracking-wide text-neutral-500">
            Backend Health
          </h2>
          <p className="font-mono text-sm">
            {JSON.stringify(health)}
          </p>
        </div>
      </main>
    </div>
  );
}
