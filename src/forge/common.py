"""Small shared helpers: timestamps and run identifiers."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone


def utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return utc_now().isoformat()


def generate_run_id() -> str:
    """Generate a sortable, unique run identifier.

    The timestamp prefix makes run directories sort chronologically; the random
    suffix keeps two runs started in the same second from colliding.
    """
    stamp = utc_now().strftime("%Y%m%dT%H%M%S")
    return f"run-{stamp}-{uuid.uuid4().hex[:8]}"
