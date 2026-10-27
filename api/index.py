"""Vercel serverless entrypoint: reuses the stdlib HTTP handler."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.api.server import H  # noqa: E402


class handler(H):  # noqa: N801 — Vercel requires a top-level `handler`
    pass
