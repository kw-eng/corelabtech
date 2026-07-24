"""Compatibility wrapper for PostgreSQL-backed session PDF reports.

The old implementation read from the legacy SQLite ``tests`` table. Reports are
now generated through ``services.session_service`` so they use PostgreSQL,
``full_sessions``, telemetry counts and the latest ``ai_results`` row.
"""

from __future__ import annotations

from pathlib import Path

from services.session_service import generate_session_report


def generate_report(
    session_id: str,
    *,
    requesting_user_id: str | None = None,
    requesting_role: str = "admin",
) -> Path:
    """Generate a PDF report for one session using the current data model."""

    return generate_session_report(
        session_id=session_id,
        requesting_user_id=requesting_user_id,
        requesting_role=requesting_role,
    )
