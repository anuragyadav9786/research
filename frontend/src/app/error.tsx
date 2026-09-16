"use client";

import Link from "next/link";
import { useEffect } from "react";

/** Next.js's error boundary for this route segment and everything under it.
 * Without this, an unhandled fetch failure (backend down, a 500) fell
 * through to Next's default unstyled error screen — every other failure
 * mode on this site (empty results, a missing fund) already gets a
 * branded, explained state; this was the one gap where it didn't. */
export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center px-4">
      <div className="text-center space-y-3 max-w-sm">
        <h1 className="text-2xl font-semibold">Something went wrong</h1>
        <p className="text-slate-400 text-sm">
          This page couldn&apos;t load its data — the backend may be temporarily unavailable. This is not a
          reflection of the funds or numbers themselves.
        </p>
        <div className="flex items-center justify-center gap-4 pt-1">
          <button
            type="button"
            onClick={reset}
            className="text-sm rounded-md border border-slate-700 bg-slate-800 px-4 py-2 hover:bg-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
          >
            Try again
          </button>
          <Link
            href="/"
            className="text-sm text-indigo-400 hover:text-indigo-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950 rounded-sm"
          >
            ← Back to Dashboard
          </Link>
        </div>
      </div>
    </div>
  );
}
