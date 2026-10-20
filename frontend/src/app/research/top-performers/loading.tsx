/** App Router's automatic Suspense fallback for this route — shown while
 * page.tsx's server-side screener fetch is in flight (switching periods
 * re-triggers this on every click, same as research/[fundId]'s loading.tsx). */
export default function TopPerformersLoading() {
  return (
    <div className="min-h-screen bg-[var(--canvas)] text-white">
      <div className="max-w-5xl mx-auto px-4 sm:px-8 py-10 space-y-6 animate-pulse">
        <div className="max-w-2xl space-y-2">
          <div className="h-8 w-48 rounded bg-white/10" />
          <div className="h-4 w-full rounded bg-white/10" />
          <div className="h-4 w-2/3 rounded bg-white/10" />
        </div>
        <div className="flex flex-wrap gap-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-8 w-20 rounded-md bg-white/10" />
          ))}
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 24 }).map((_, i) => (
            <div key={i} className="rounded-lg border border-white/10 bg-[var(--surface-1)] p-4 space-y-3">
              <div className="h-4 w-3/4 rounded bg-white/15" />
              <div className="h-3 w-1/3 rounded bg-white/15" />
              <div className="h-6 w-20 rounded bg-white/15" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
