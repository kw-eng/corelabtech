"""Report service facade.

Keep this module as the public service import point for report generation while
delegating the actual PostgreSQL-backed PDF rendering to session_service.
"""

from __future__ import annotations

from pathlib import Path

from services.session_service import generate_session_report


def generate_report_for_session(
    *,
    session_id: str,
    requesting_user_id: str | None,
    requesting_role: str,
    requesting_organization_id: int | None = None,
) -> Path:
    return generate_session_report(
        session_id=session_id,
        requesting_user_id=requesting_user_id,
        requesting_role=requesting_role,
        requesting_organization_id=requesting_organization_id,
    )
