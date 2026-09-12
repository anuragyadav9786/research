import Link from "next/link";

export default function NotFound() {
  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-100 flex items-center justify-center">
      <div className="text-center space-y-3">
        <h1 className="text-2xl font-semibold">Not found</h1>
        <p className="text-neutral-400 text-sm">This page, or the fund it refers to, doesn&apos;t exist.</p>
        <Link href="/research" className="inline-block text-sm text-cyan-400 hover:text-cyan-300">
          ← Back to Research
        </Link>
      </div>
    </div>
  );
}
