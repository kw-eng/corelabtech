"""Report generation orchestration service.

Routes should use this module as the public boundary for downloadable reports.
The lower-level PDF layout still lives in ``session_service`` for now, but path
creation, file naming, series data loading and audit payloads are centralized
here so HTTP handlers stay small.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from auth.access_policy import can_access_client_record
from services.series_service import get_user_series_trends
from services.session_service import (
    build_series_pdf_report,
    generate_session_report,
    get_research_session,
    safe_filename,
)


REPORTS_DIRECTORY = Path("reports/generated")


@dataclass(frozen=True)
class ReportExport:
    """Generated report file plus route-level audit metadata."""

    path: Path
    download_name: str
    audit_action: str
    audit_entity_type: str
    audit_entity_id: str
    audit_client_id: str | None
    audit_session_id: str | None
    audit_details: dict[str, Any]


def generate_report_for_session(
    *,
    session_id: str,
    requesting_user_id: str | None,
    requesting_role: str,
    requesting_organization_id: int | None = None,
) -> ReportExport:
    """Generate a single-session PDF and return export metadata."""

    path = generate_session_report(
        session_id=session_id,
        requesting_user_id=requesting_user_id,
        requesting_role=requesting_role,
        requesting_organization_id=requesting_organization_id,
    )
    session = get_research_session(
        session_id=session_id,
        requesting_user_id=requesting_user_id,
        requesting_role=requesting_role,
        requesting_organization_id=requesting_organization_id,
    )
    client_id = None

    if session:
        client_id = session.get("client_id") or session.get("user_id")

    return ReportExport(
        path=path,
        download_name=f"corelabtech_{safe_filename(session_id)}_report.pdf",
        audit_action="report.export",
        audit_entity_type="session",
        audit_entity_id=session_id,
        audit_client_id=client_id,
        audit_session_id=session_id,
        audit_details={
            "format": "pdf",
            "report_type": "single_session",
            "filename": path.name,
        },
    )


def generate_series_report_for_client(
    *,
    user_id: str,
    requesting_user_id: str | None,
    requesting_role: str,
    requesting_organization_id: int | None = None,
    protocol_id: int | None = None,
    trend_limit: int = 25,
) -> ReportExport:
    """Generate a PDF report for a client's longitudinal session series."""

    if not can_access_client_record(
        requesting_role=requesting_role,
        requesting_user_id=requesting_user_id,
        client_id=user_id,
        requesting_organization_id=requesting_organization_id,
    ):
        raise PermissionError("forbidden")

    series_data = get_user_series_trends(
        user_id=user_id,
        protocol_id=protocol_id,
        trend_limit=trend_limit,
    )
    REPORTS_DIRECTORY.mkdir(parents=True, exist_ok=True)

    safe_subject_id = safe_filename(user_id) or "client"
    path = REPORTS_DIRECTORY / (
        f"corelabtech_{safe_subject_id}_series_{trend_limit}_report.pdf"
    )

    build_series_pdf_report(
        path=path,
        series_data=series_data,
    )

    return ReportExport(
        path=path,
        download_name=path.name,
        audit_action="series_report.export",
        audit_entity_type="client_series",
        audit_entity_id=user_id,
        audit_client_id=user_id,
        audit_session_id=None,
        audit_details={
            "format": "pdf",
            "report_type": "session_series",
            "series_limit": trend_limit,
            "records": series_data.get("records"),
            "filename": path.name,
        },
    )
