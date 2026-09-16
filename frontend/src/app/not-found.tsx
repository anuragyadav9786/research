import Link from "next/link";

export default function NotFound() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center">
      <div className="text-center space-y-3">
        <h1 className="text-2xl font-semibold">Not found</h1>
        <p className="text-slate-400 text-sm">This page, or the fund it refers to, doesn&apos;t exist.</p>
        <Link href="/research" className="inline-block text-sm text-indigo-500 hover:text-indigo-600">
          ← Back to Research
        </Link>
      </div>
    </div>
  );
}
