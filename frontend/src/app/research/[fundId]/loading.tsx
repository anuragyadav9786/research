/** Next.js renders this automatically the instant a fund's research page
 * is navigated to, for as long as page.tsx's server-side data fetching is
 * in flight — no client-side wiring needed, App Router treats a
 * `loading.tsx` sibling as this route segment's Suspense fallback.
 *
 * Worth having specifically because of the lazy per-scheme NAV backfill
 * (data_pipeline/orchestration/lazy_nav_backfill.py): a fund's FIRST view
 * ever triggers a real fetch to api.mfapi.in before any of the page's
 * seven parallel analytics calls can return, which can take several
 * seconds — long enough that a silent blank tab reads as broken. Every
 * later view of the same fund is a fast local query and this screen will
 * barely flash.
 */
export default function FundDetailLoading() {
  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-100 flex items-center justify-center px-6">
      <div className="max-w-sm text-center space-y-4">
        <div
          className="mx-auto h-8 w-8 rounded-full border-2 border-neutral-700 border-t-cyan-400 animate-spin"
          role="status"
          aria-label="Loading"
        />
        <p className="text-sm text-neutral-300">Loading fund research…</p>
        <p className="text-xs text-neutral-500 leading-relaxed">
          If this is the first time anyone&rsquo;s viewed this fund, we&rsquo;re fetching its full historical
          NAV record — this can take a few seconds. Every visit after this one will be instant.
        </p>
      </div>
    </div>
  );
}
