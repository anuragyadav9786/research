"""Entry point for applying benchmark_curation.py's manual category/scheme
-> benchmark mapping to the database, run as:

    python -m data_pipeline.orchestration.apply_benchmark_curation

with DATABASE_URL pointing at the same database the backend uses. Safe to
re-run — only fills schemes with no existing benchmark assignment (see
benchmark_curation.py's own docstring on why it never overwrites).
"""
from __future__ import annotations

import os
import sys

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from app.core.database import SessionLocal  # noqa: E402
from data_pipeline.normalization.benchmark_curation import apply_manual_benchmark_curation  # noqa: E402


def main() -> None:
    db = SessionLocal()
    try:
        result = apply_manual_benchmark_curation(db)
        print(
            f"Benchmark curation: schemes_assigned={result.schemes_assigned} "
            f"benchmarks_created={result.benchmarks_created} "
            f"schemes_skipped_already_mapped={result.schemes_skipped_already_mapped} "
            f"schemes_skipped_no_mapping={result.schemes_skipped_no_mapping}"
        )
        for name in result.assigned_scheme_names[:20]:
            print(f"  assigned: {name!r}")
        if len(result.assigned_scheme_names) > 20:
            print(f"  ... and {len(result.assigned_scheme_names) - 20} more")
    finally:
        db.close()


if __name__ == "__main__":
    main()
