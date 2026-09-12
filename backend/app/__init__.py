"""Ensures the repo-root packages (analytics/, data_pipeline/) are
importable from anywhere under the `app` package, regardless of entry
point (uvicorn, a script, alembic, pytest) or working directory — mirrors
the same sys.path pattern database/migrations/env.py already uses in the
opposite direction (backend/ -> alembic)."""
import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
