"""Make the repo-root packages (analytics/, data_pipeline/) importable from
tests run inside backend/, without duplicating that code under backend/app."""
import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
