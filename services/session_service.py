"""Session persistence and PDF reporting service.

Routes call this module to save PRE/DURING/POST phase data, complete research
sessions, list session ownership safely, delete sessions and generate reports.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from auth.access_policy import (
    CLIENT_STAFF_ROLES,
    can_access_client_record,
)
from core.pressure import calculate_pressure_ata
from database_postgres import db
from repositories.wellness_repository import get_wellness_summary
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

SESSION_CLIENT_TABLES = (
    "tests",
    "fit_imports",
    "csv_imports",
    "fit_data",
    "csv_data",
    "merge_jobs",
    "merged_data",
    "ai_results",
    "session_features",
    "hrv_imports",
    "hrv_intervals",
)
@dataclass(frozen=True)
class PhaseResult:
    """Database identity of one saved phase row."""

    phase_id: int
    session_id: str
    phase: str


@dataclass(frozen=True)
class CompletedSessionResult:
    """Summary returned after the full session payload is stored."""

    session_id: str
    user_id: str
    fit_samples: int
    csv_samples: int
    merged_samples: int
    features: dict[str, Any]

def save_session_phase(
    *,
    payload: dict[str, Any],
    initiated_by: str | None = None,
) -> PhaseResult:
    """Persist one PRE, DURING or POST phase measurement package."""

    session_id = required_text(payload.get("session_id"), "session_id")
    phase = required_text(payload.get("phase"), "phase")
    explicit_client_id = optional_text(
        payload.get("client_id")
        or payload.get("user_id")
    )
    user_id = (
        explicit_client_id
        or normalize_subject_id(initiated_by or session_id)
    )
    telemetry = payload.get("telemetry") or payload

    connection = db()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO tests (
                session_id,
                user_id,
                phase,
                device,
                status,
                spo2,
                pulse,
                hrv,
                pressure,
                pressure_ata,
                ata,
                oxygen_flow_lpm,
                oxygen_percent,
                temperature,
                body_temperature,
                humidity,
                telemetry_json,
                source
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s
            )
            RETURNING id
            """,
            (
                session_id,
                user_id,
                phase,
                payload.get("device"),
                payload.get("status"),
                number_or_none(payload.get("spo2")),
                number_or_none(payload.get("pulse")),
                number_or_none(payload.get("hrv")),
                number_or_none(
                    payload.get("pressure_input_value")
                    or payload.get("pressure_kpa")
                    or payload.get("pressure")
                ),
                number_or_none(payload.get("pressure_ata")),
                number_or_none(
                    payload.get("ata")
                    or payload.get("pressure_ata")
                ),
                number_or_none(payload.get("oxygen_flow_lpm")),
                number_or_none(
                    payload.get("oxygen_percent")
                    or payload.get("oxygen_mask_percent")
                ),
                number_or_none(
                    payload.get("temperature")
                    or payload.get("chamber_temperature")
                ),
                number_or_none(payload.get("body_temperature")),
                number_or_none(payload.get("humidity")),
                json.dumps(telemetry, default=str),
                payload.get("source") or "research_phase",
            ),
        )

        phase_id = cursor.fetchone()[0]
        connection.commit()

        return PhaseResult(
            phase_id=phase_id,
            session_id=session_id,
            phase=phase,
        )

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()


def complete_session(
    *,
    session_id: str,
    user_id: str,
    pre: dict[str, Any],
    during: dict[str, Any],
    post: dict[str, Any],
    initiated_by: str | None = None,
) -> CompletedSessionResult:
    """Create or update the canonical completed session record."""

    session_id = required_text(session_id, "session_id")
    user_id = required_text(user_id, "user_id")

    connection = db()
    cursor = connection.cursor()

    try:
        ensure_user(cursor, user_id=user_id)
        session_config = resolve_session_configuration(
            cursor,
            during=during,
            user_id=user_id,
        )

        cursor.execute(
            """
            INSERT INTO full_sessions (
                session_id,
                user_id,
                session_status,
                pre_json,
                during_json,
                post_json,
                summary,
                completed,
                chamber_id,
                protocol_id,
                target_ata,
                actual_ata,
                pressure_input_value,
                pressure_input_unit,
                pressure_deviation,
                compression_time_min,
                exposure_time_min,
                decompression_time_min,
                total_duration_min,
                organization_id,
                location_id,
                program_enrollment_id,
                protocol_version,
                execution_status,
                deviation_reason,
                deviation_approved_by
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (session_id)
            DO UPDATE SET
                user_id = EXCLUDED.user_id,
                session_status = EXCLUDED.session_status,
                pre_json = EXCLUDED.pre_json,
                during_json = EXCLUDED.during_json,
                post_json = EXCLUDED.post_json,
                summary = EXCLUDED.summary,
                completed = EXCLUDED.completed,
                chamber_id = EXCLUDED.chamber_id,
                protocol_id = EXCLUDED.protocol_id,
                target_ata = EXCLUDED.target_ata,
                actual_ata = EXCLUDED.actual_ata,
                pressure_input_value = EXCLUDED.pressure_input_value,
                pressure_input_unit = EXCLUDED.pressure_input_unit,
                pressure_deviation = EXCLUDED.pressure_deviation,
                compression_time_min = EXCLUDED.compression_time_min,
                exposure_time_min = EXCLUDED.exposure_time_min,
                decompression_time_min = EXCLUDED.decompression_time_min,
                total_duration_min = EXCLUDED.total_duration_min,
                organization_id = EXCLUDED.organization_id,
                location_id = EXCLUDED.location_id,
                program_enrollment_id = EXCLUDED.program_enrollment_id,
                protocol_version = EXCLUDED.protocol_version,
                execution_status = EXCLUDED.execution_status,
                deviation_reason = EXCLUDED.deviation_reason,
                deviation_approved_by = EXCLUDED.deviation_approved_by
            """,
            (
                session_id,
                user_id,
                "completed",
                json.dumps(pre, default=str),
                json.dumps(during, default=str),
                json.dumps(post, default=str),
                json.dumps(
                    {
                        "completed_by": initiated_by,
                        "source": "research_routes",
                    },
                    default=str,
                ),
                1,
                session_config["chamber_id"],
                session_config["protocol_id"],
                session_config["target_ata"],
                session_config["actual_ata"],
                session_config["pressure_input_value"],
                session_config["pressure_input_unit"],
                session_config["pressure_deviation"],
                session_config["compression_time_min"],
                session_config["exposure_time_min"],
                session_config["decompression_time_min"],
                session_config["total_duration_min"],
                session_config["organization_id"],
                session_config["location_id"],
                session_config["program_enrollment_id"],
                session_config["protocol_version"],
                session_config["execution_status"],
                session_config["deviation_reason"],
                initiated_by if session_config["requires_approval"] else None,
            ),
        )

        save_session_segments(
            cursor,
            session_id=session_id,
            segments=session_config["segments"],
        )

        align_session_client_ownership(
            cursor,
            session_id=session_id,
            client_id=user_id,
        )

        features = {
    "avg_csv_spo2": average_from_payload(during, "spo2"),
    "avg_csv_pulse": average_from_payload(during, "pulse"),
}
        result = CompletedSessionResult(
            session_id=session_id,
            user_id=user_id,
            fit_samples=count_rows(
                cursor,
                table="fit_data",
                session_id=session_id,
            ),
            csv_samples=count_rows(
                cursor,
                table="csv_data",
                session_id=session_id,
            ),
            merged_samples=count_rows(
                cursor,
                table="merged_data",
                session_id=session_id,
            ),
            features=features,
        )

        connection.commit()

        return result

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()


def align_session_client_ownership(
    cursor,
    *,
    session_id: str,
    client_id: str,
) -> None:
    """Keep every persisted stage of a session assigned to one client."""

    for table in SESSION_CLIENT_TABLES:
        cursor.execute(
            f"""
            UPDATE {table}
            SET user_id = %s
            WHERE session_id = %s
              AND user_id IS DISTINCT FROM %s
            """,
            (
                client_id,
                session_id,
                client_id,
            ),
        )


def list_research_sessions(
    *,
    requesting_user_id: str | None,
    requesting_role: str,
    requesting_organization_id: int | None = None,
) -> list[dict[str, Any]]:
    """List sessions visible to the current user role."""

    connection = db()
    cursor = connection.cursor()

    try:
        if requesting_role == "admin":
            cursor.execute(
                """
                SELECT
                    fs.session_id,
                    fs.user_id,
                    fs.session_status,
                    fs.completed,
                    fs.created_at,
                    p.name,
                    fs.actual_ata
                FROM full_sessions fs
                LEFT JOIN protocols p
                    ON p.protocol_id = fs.protocol_id
                WHERE fs.session_id NOT LIKE 'PIPELINE_VALIDATION_%%'
                ORDER BY fs.created_at DESC
                """
            )
        elif requesting_role in CLIENT_STAFF_ROLES:
            cursor.execute(
                """
                SELECT
                    fs.session_id,
                    fs.user_id,
                    fs.session_status,
                    fs.completed,
                    fs.created_at,
                    p.name
                    ,fs.actual_ata
                FROM full_sessions fs
                LEFT JOIN protocols p
                    ON p.protocol_id = fs.protocol_id
                WHERE fs.organization_id = %s
                  AND fs.session_id NOT LIKE 'PIPELINE_VALIDATION_%%'
                ORDER BY fs.created_at DESC
                """,
                (requesting_organization_id,),
            )
        else:
            cursor.execute(
                """
                SELECT
                    fs.session_id,
                    fs.user_id,
                    fs.session_status,
                    fs.completed,
                    fs.created_at,
                    p.name,
                    fs.actual_ata
                FROM full_sessions fs
                LEFT JOIN protocols p
                    ON p.protocol_id = fs.protocol_id
                WHERE fs.user_id = %s
                  AND fs.session_id NOT LIKE 'PIPELINE_VALIDATION_%%'
                ORDER BY fs.created_at DESC
                """,
                (requesting_user_id,),
            )

        return [
            {
                "session_id": row[0],
                "user_id": row[1],
                "client_id": row[1],
                "status": row[2],
                "completed": bool(row[3]),
                "created_at": row[4].isoformat() if row[4] else None,
                "protocol_name": row[5],
                "actual_ata": row[6],
            }
            for row in cursor.fetchall()
        ]

    finally:
        cursor.close()
        connection.close()


def get_research_session(
    *,
    session_id: str,
    requesting_user_id: str | None,
    requesting_role: str,
    requesting_organization_id: int | None = None,
) -> dict[str, Any] | None:
    """Load one session and enforce owner access for non-admin users."""

    connection = db()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT
                session_id,
                user_id,
                session_status,
                pre_json,
                during_json,
                post_json,
                summary,
                completed,
                fs.created_at,
                fs.chamber_id,
                fs.protocol_id,
                fs.target_ata,
                fs.actual_ata,
                fs.pressure_input_value,
                fs.pressure_input_unit,
                fs.pressure_deviation,
                p.name,
                c.name,
                fs.compression_time_min,
                fs.exposure_time_min,
                fs.decompression_time_min,
                fs.total_duration_min,
                fs.execution_status,
                fs.deviation_reason,
                fs.program_enrollment_id,
                fs.protocol_version,
                fs.organization_id,
                fs.location_id
            FROM full_sessions fs
            LEFT JOIN protocols p
                ON p.protocol_id = fs.protocol_id
            LEFT JOIN chambers c
                ON c.chamber_id = fs.chamber_id
            WHERE fs.session_id = %s
            LIMIT 1
            """,
            (session_id,),
        )

        row = cursor.fetchone()

        if not row:
            return None

        if not can_access_client_record(
            requesting_role=requesting_role,
            requesting_user_id=requesting_user_id,
            client_id=row[1],
            requesting_organization_id=requesting_organization_id,
        ):
            return None

        result = {
            "session_id": row[0],
            "user_id": row[1],
            "client_id": row[1],
            "status": row[2],
            "pre": json_loads(row[3]),
            "during": json_loads(row[4]),
            "post": json_loads(row[5]),
            "summary": json_loads(row[6]),
            "completed": bool(row[7]),
            "created_at": row[8].isoformat() if row[8] else None,
            "chamber_id": row[9],
            "protocol_id": row[10],
            "target_ata": row[11],
            "actual_ata": row[12],
            "pressure_input_value": row[13],
            "pressure_input_unit": row[14],
            "pressure_deviation": row[15],
            "protocol_name": row[16],
            "chamber_name": row[17],
            "compression_time_min": row[18],
            "exposure_time_min": row[19],
            "decompression_time_min": row[20],
            "total_duration_min": row[21],
            "execution_status": row[22],
            "deviation_reason": row[23],
            "program_enrollment_id": row[24],
            "protocol_version": row[25],
            "organization_id": row[26],
            "location_id": row[27],
        }
        cursor.execute(
            """
            SELECT
                sequence_no,
                phase,
                planned_duration_min,
                actual_duration_min,
                target_ata,
                actual_ata,
                oxygen_mode,
                note
            FROM session_segments
            WHERE session_id = %s
            ORDER BY sequence_no
            """,
            (session_id,),
        )
        result["segments"] = [
            {
                "sequence_no": segment[0],
                "phase": segment[1],
                "planned_duration_min": segment[2],
                "actual_duration_min": segment[3],
                "target_ata": segment[4],
                "actual_ata": segment[5],
                "oxygen_mode": segment[6],
                "note": segment[7],
            }
            for segment in cursor.fetchall()
        ]
        return result

    finally:
        cursor.close()
        connection.close()


def delete_research_sessions(
    *,
    session_ids: list[str],
) -> int:
    """Delete completed session records by id and return how many were removed."""

    clean_ids = [
        str(session_id).strip()
        for session_id in session_ids
        if str(session_id).strip()
    ]

    if not clean_ids:
        return 0

    connection = db()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            DELETE FROM full_sessions
            WHERE session_id = ANY(%s)
            """,
            (clean_ids,),
        )
        deleted = cursor.rowcount
        connection.commit()
        return deleted

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()


def generate_session_report(
    *,
    session_id: str,
    requesting_user_id: str | None,
    requesting_role: str,
    requesting_organization_id: int | None = None,
) -> Path:
    """Build a PDF report for one authorized session."""

    session = get_research_session(
        session_id=session_id,
        requesting_user_id=requesting_user_id,
        requesting_role=requesting_role,
        requesting_organization_id=requesting_organization_id,
    )

    if not session:
        raise FileNotFoundError("session not found")

    report_data = load_report_data(session_id=session_id)

    reports_dir = Path("reports/generated")
    reports_dir.mkdir(parents=True, exist_ok=True)

    path = reports_dir / f"corelabtech_{safe_filename(session_id)}_report.pdf"
    build_pdf_report(
        path=path,
        session=session,
        report_data=report_data,
    )

    return path


def load_report_data(*, session_id: str) -> dict[str, Any]:
    """Load counts and latest AI analysis needed by the PDF report."""

    connection = db()
    cursor = connection.cursor()

    try:
        counts = {
            "fit_samples": count_rows(
                cursor,
                table="fit_data",
                session_id=session_id,
            ),
            "csv_samples": count_rows(
                cursor,
                table="csv_data",
                session_id=session_id,
            ),
            "merged_samples": count_rows(
                cursor,
                table="merged_data",
                session_id=session_id,
            ),
        }

        cursor.execute(
            """
            SELECT
                fs.user_id,
                u.email,
                u.sex,
                u.age,
                u.weight,
                u.notes,
                fs.protocol_id,
                fs.target_ata,
                fs.actual_ata,
                fs.pressure_deviation,
                fs.pressure_input_value,
                fs.pressure_input_unit,
                p.code,
                p.name,
                p.planned_duration_min,
                c.code,
                c.name,
                c.location,
                fs.compression_time_min,
                fs.exposure_time_min,
                fs.decompression_time_min,
                fs.total_duration_min,
                o.name,
                ol.name,
                wp.name,
                wp.total_sessions,
                (
                    SELECT COUNT(*)
                    FROM full_sessions completed_fs
                    WHERE completed_fs.program_enrollment_id =
                        fs.program_enrollment_id
                      AND completed_fs.completed = 1
                )
            FROM full_sessions fs
            LEFT JOIN users u
                ON u.user_id = fs.user_id
            LEFT JOIN protocols p
                ON p.protocol_id = fs.protocol_id
            LEFT JOIN chambers c
                ON c.chamber_id = fs.chamber_id
            LEFT JOIN organizations o
                ON o.organization_id = fs.organization_id
            LEFT JOIN organization_locations ol
                ON ol.location_id = fs.location_id
            LEFT JOIN client_programs cp
                ON cp.enrollment_id = fs.program_enrollment_id
            LEFT JOIN wellness_programs wp
                ON wp.program_id = cp.program_id
            WHERE fs.session_id = %s
            LIMIT 1
            """,
            (session_id,),
        )

        subject_row = cursor.fetchone()
        subject = None

        if subject_row:
            subject = {
                "user_id": subject_row[0],
                "email": subject_row[1],
                "sex": subject_row[2],
                "age": subject_row[3],
                "weight": subject_row[4],
                "notes": subject_row[5],
            }
            session_config = {
                "protocol_id": subject_row[6],
                "target_ata": subject_row[7],
                "actual_ata": subject_row[8],
                "pressure_deviation": subject_row[9],
                "pressure_input_value": subject_row[10],
                "pressure_input_unit": subject_row[11],
                "protocol_code": subject_row[12],
                "protocol_name": subject_row[13],
                "planned_duration_min": subject_row[14],
                "chamber_code": subject_row[15],
                "chamber_name": subject_row[16],
                "location": subject_row[17],
                "compression_time_min": subject_row[18],
                "exposure_time_min": subject_row[19],
                "decompression_time_min": subject_row[20],
                "total_duration_min": subject_row[21],
                "organization_name": subject_row[22],
                "location_name": subject_row[23],
                "program_name": subject_row[24],
                "program_total_sessions": subject_row[25],
                "program_completed_sessions": subject_row[26],
            }
        else:
            session_config = None

        cursor.execute(
            """
            SELECT
                ai_result_id,
                merge_id,
                model_name,
                model_version,
                overall_score,
                stress_score,
                hypoxia_score,
                cardiovascular_score,
                data_quality_score,
                anomaly_detected,
                stress_detected,
                hypoxia_detected,
                arrhythmia_detected,
                summary,
                recommendations,
                features_json,
                result_json,
                created_at
            FROM ai_results
            WHERE session_id = %s
            ORDER BY created_at DESC, ai_result_id DESC
            LIMIT 1
            """,
            (session_id,),
        )

        row = cursor.fetchone()

        analysis = None

        if row:
            analysis = {
                "ai_result_id": row[0],
                "merge_id": row[1],
                "model_name": row[2],
                "model_version": row[3],
                "overall_score": row[4],
                "stress_score": row[5],
                "hypoxia_score": row[6],
                "cardiovascular_score": row[7],
                "data_quality_score": row[8],
                "anomaly_detected": bool(row[9]),
                "stress_detected": bool(row[10]),
                "hypoxia_detected": bool(row[11]),
                "arrhythmia_detected": bool(row[12]),
                "summary": row[13],
                "recommendations": row[14],
                "features": row[15] or {},
                "result": row[16] or {},
                "created_at": row[17].isoformat() if row[17] else None,
            }

        wellness_history = (
            get_wellness_summary(
                cursor,
                user_id=subject["user_id"],
                protocol_id=(
                    session_config.get("protocol_id")
                    if session_config
                    else None
                ),
            )
            if subject
            else None
        )

        return {
            **counts,
            "subject": subject,
            "session_config": session_config,
            "analysis": analysis,
            "wellness_history": wellness_history,
        }

    finally:
        cursor.close()
        connection.close()


def build_pdf_report(
    *,
    path: Path,
    session: dict[str, Any],
    report_data: dict[str, Any],
) -> None:
    """Render report data into a compact PDF document."""

    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        title=f"CoreLabTech wellness report {session['session_id']}",
    )

    story = [
        Paragraph("CoreLabTech Wellness Session Report", styles["Title"]),
        Spacer(1, 12),
        Paragraph("Session Summary", styles["Heading2"]),
        make_table(
            [
                ("Session ID", session.get("session_id")),
                ("Client ID", session.get("user_id")),
                ("Status", session.get("status")),
                ("Completed", session.get("completed")),
                ("Created at", session.get("created_at")),
                (
                    "Organization",
                    (report_data.get("session_config") or {}).get(
                        "organization_name"
                    ),
                ),
                (
                    "Location",
                    (report_data.get("session_config") or {}).get(
                        "location_name"
                    ),
                ),
                ("Chamber", session.get("chamber_name")),
                ("Protocol", session.get("protocol_name")),
                ("Protocol version", session.get("protocol_version")),
                (
                    "Program",
                    (report_data.get("session_config") or {}).get(
                        "program_name"
                    ),
                ),
                (
                    "Program progress",
                    (
                        f"{(report_data.get('session_config') or {}).get('program_completed_sessions')}/"
                        f"{(report_data.get('session_config') or {}).get('program_total_sessions')}"
                        if (report_data.get("session_config") or {}).get(
                            "program_name"
                        )
                        else "-"
                    ),
                ),
                ("Execution status", session.get("execution_status")),
                ("Deviation reason", session.get("deviation_reason")),
                ("Target ATA", session.get("target_ata")),
                ("Recorded ATA", session.get("actual_ata")),
                ("ATA difference", session.get("pressure_deviation")),
                (
                    "Planned total time (min)",
                    (report_data.get("session_config") or {}).get(
                        "planned_duration_min"
                    ),
                ),
                (
                    "Actual compression (min)",
                    session.get("compression_time_min"),
                ),
                (
                    "Actual time at target pressure (min)",
                    session.get("exposure_time_min"),
                ),
                (
                    "Actual decompression (min)",
                    session.get("decompression_time_min"),
                ),
                ("Actual total time (min)", session.get("total_duration_min")),
            ]
        ),
        Spacer(1, 12),
        Paragraph("Session Timeline", styles["Heading2"]),
        make_table(
            [
                (
                    f"{segment.get('sequence_no')}. "
                    f"{str(segment.get('phase') or '').replace('_', ' ').title()}",
                    (
                        f"{segment.get('actual_duration_min')} min; "
                        f"ATA {segment.get('actual_ata') or '-'}; "
                        f"{segment.get('note') or 'no note'}"
                    ),
                )
                for segment in session.get("segments") or []
            ]
            or [("Timeline", "No segment data available")]
        ),
        Spacer(1, 12),
        Paragraph("Client", styles["Heading2"]),
        make_table(
            [
                ("Client ID", (report_data.get("subject") or {}).get("user_id")),
                ("Email", (report_data.get("subject") or {}).get("email")),
                ("Sex", (report_data.get("subject") or {}).get("sex")),
                ("Age", (report_data.get("subject") or {}).get("age")),
                ("Weight", (report_data.get("subject") or {}).get("weight")),
                ("Notes", (report_data.get("subject") or {}).get("notes")),
            ]
        ),
        Spacer(1, 12),
        Paragraph("Data Sources", styles["Heading2"]),
        make_table(
            [
                ("HR/HRV Timeline samples", report_data.get("fit_samples")),
                ("SpO2/Pulse Timeline samples", report_data.get("csv_samples")),
                ("Synchronized samples", report_data.get("merged_samples")),
            ]
        ),
        Spacer(1, 12),
        Paragraph("Check-in / Session / Recovery", styles["Heading2"]),
        make_table(
            [
                ("Check-in SpO2", phase_metric(session.get("pre"), "spo2", "avg_spo2")),
                ("Check-in pulse / HR", phase_metric(session.get("pre"), "pulse", "hr", "heart_rate")),
                ("Check-in HRV", phase_metric(session.get("pre"), "hrv", "rmssd", "avg_hrv")),
                ("Check-in context", format_context(phase_metric(session.get("pre"), "check_in"))),
                (
                    "Wellness acknowledgement",
                    format_context(
                        phase_metric(
                            session.get("pre"),
                            "wellness_consent",
                        )
                    ),
                ),
                ("Session avg SpO2", phase_metric(session.get("during"), "avg_spo2", "spo2")),
                ("Session min SpO2", phase_metric(session.get("during"), "min_spo2")),
                ("Session avg pulse / HR", phase_metric(session.get("during"), "avg_pulse", "avg_hr", "pulse", "hr")),
                ("Session avg HRV", phase_metric(session.get("during"), "avg_hrv", "rmssd", "hrv")),
                ("Session pressure", phase_metric(session.get("during"), "pressure_ata", "ata")),
                ("Session temperature", phase_metric(session.get("during"), "chamber_temperature", "temperature")),
                ("Session oxygen flow", phase_metric(session.get("during"), "oxygen_flow_lpm")),
                ("Session oxygen setting", phase_metric(session.get("during"), "oxygen_mask_percent", "oxygen_percent")),
                ("Recovery SpO2", phase_metric(session.get("post"), "spo2", "avg_spo2")),
                ("Recovery pulse / HR", phase_metric(session.get("post"), "pulse", "hr", "heart_rate")),
                ("Recovery HRV", phase_metric(session.get("post"), "hrv", "rmssd", "avg_hrv")),
                ("Recovery context", format_context(phase_metric(session.get("post"), "check_out"))),
            ]
        ),
    ]

    wellness_history = report_data.get("wellness_history") or {}
    baseline = wellness_history.get("baseline") or {}

    story.extend(
        [
            Spacer(1, 12),
            Paragraph("Personal Baseline", styles["Heading2"]),
            make_table(
                [
                    (
                        "Baseline confidence",
                        wellness_history.get("baseline_confidence"),
                    ),
                    (
                        "Unique sessions (30 days)",
                        wellness_history.get("unique_sessions_30d"),
                    ),
                    ("RMSSD 7 days", baseline.get("rmssd_7d")),
                    ("RMSSD 14 days", baseline.get("rmssd_14d")),
                    ("RMSSD 30 days", baseline.get("rmssd_30d")),
                    (
                        "Session HR reference (7 days)",
                        baseline.get("resting_hr_7d"),
                    ),
                    ("SpO2 average", baseline.get("spo2_avg")),
                    ("SpO2 minimum", baseline.get("spo2_min")),
                    (
                        "Baseline data quality",
                        baseline.get("data_quality_score"),
                    ),
                ]
            ),
        ]
    )

    analysis = report_data.get("analysis")

    story.extend(
        [
            Spacer(1, 12),
            Paragraph("Wellness Analysis", styles["Heading2"]),
        ]
    )

    if analysis:
        analysis_result = analysis.get("result") or {}
        wellness_flags = analysis_result.get("wellness_flags") or {}
        quality_warnings = analysis_result.get("quality_warnings") or []

        story.append(
            make_table(
                [
                    ("Analysis result ID", analysis.get("ai_result_id")),
                    ("Merge ID", analysis.get("merge_id")),
                    ("Model", analysis.get("model_name")),
                    ("Model version", analysis.get("model_version")),
                    ("Product mode", analysis_result.get("product_mode", "wellness")),
                    ("Wellness status", analysis_result.get("wellness_status")),
                    ("Wellness response", analysis.get("overall_score")),
                    ("Load score", analysis.get("stress_score")),
                    ("Oxygenation minimum", analysis.get("hypoxia_score")),
                    (
                        "Heart-rate peak",
                        analysis.get("cardiovascular_score"),
                    ),
                    ("Data quality score", analysis.get("data_quality_score")),
                    ("Data quality warnings", format_list(quality_warnings)),
                    (
                        "Session review recommended",
                        analysis_result.get(
                            "session_flagged",
                            analysis.get("anomaly_detected"),
                        ),
                    ),
                    (
                        "Elevated load flag",
                        wellness_flags.get(
                            "elevated_load",
                            analysis.get("stress_detected"),
                        ),
                    ),
                    (
                        "Low oxygenation trend flag",
                        wellness_flags.get(
                            "oxygenation_drop",
                            analysis.get("hypoxia_detected"),
                        ),
                    ),
                    (
                        "Sensor alignment warning",
                        wellness_flags.get(
                            "sensor_alignment_warning",
                            False,
                        ),
                    ),
                    ("Created at", analysis.get("created_at")),
                ]
            )
        )

        story.extend(
            [
                Spacer(1, 10),
                Paragraph("Summary", styles["Heading3"]),
                Paragraph(escape_text(analysis.get("summary")), styles["BodyText"]),
                Spacer(1, 8),
                Paragraph("Recommendations", styles["Heading3"]),
                Paragraph(
                    escape_text(analysis.get("recommendations")),
                    styles["BodyText"],
                ),
            ]
        )
    else:
        story.append(
            Paragraph(
                "No wellness analysis result is available for this session yet.",
                styles["BodyText"],
            )
        )

    story.extend(
        [
            Spacer(1, 12),
            Paragraph("Wellness Notice", styles["Heading2"]),
            Paragraph(
                "This report provides wellness and educational insights only. "
                "It is not intended to diagnose, treat, cure, or prevent disease. "
                "It should be interpreted together with session context, sensor quality "
                "and professional judgement where appropriate.",
                styles["BodyText"],
            ),
        ]
    )

    doc.build(story)


def make_table(rows: list[tuple[str, Any]]) -> Table:
    """Create a consistently styled two-column report table."""

    table = Table(
        [
            [
                Paragraph(str(label), getSampleStyleSheet()["BodyText"]),
                Paragraph(escape_text(value), getSampleStyleSheet()["BodyText"]),
            ]
            for label, value in rows
        ],
        colWidths=[150, 330],
    )

    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f2f4f7")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c9ced6")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )

    return table


def escape_text(value: Any) -> str:
    """Escape text before placing it inside reportlab Paragraph markup."""

    if value is None:
        return "-"

    text = str(value)

    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def phase_metric(phase: Any, *keys: str) -> Any:
    """Return a readable value from nested PRE/DURING/POST payloads."""

    if not isinstance(phase, dict):
        return None

    for key in keys:
        value = nested_get(phase, key)

        if value not in (None, ""):
            return value

    return None


def nested_get(payload: dict[str, Any], key: str) -> Any:
    """Find a key inside common telemetry/feature nesting patterns."""

    if key in payload:
        return payload[key]

    for nested_key in (
        "telemetry",
        "features",
        "summary",
        "data",
        "metrics",
    ):
        nested = payload.get(nested_key)

        if isinstance(nested, dict) and key in nested:
            return nested[key]

    return None


def format_list(values: Any) -> str:
    """Format warnings and flags for compact PDF output."""

    if not values:
        return "-"

    if isinstance(values, (list, tuple, set)):
        return ", ".join(str(value) for value in values) or "-"

    return str(values)


def format_context(value: Any) -> str:
    """Format optional check-in/check-out context for the PDF."""

    if not isinstance(value, dict):
        return "-"

    pairs = [
        f"{key.replace('_', ' ')}: {item}"
        for key, item in value.items()
        if item not in (None, "")
    ]

    return "; ".join(pairs) if pairs else "-"


def safe_filename(value: str) -> str:
    """Convert a session id into a filesystem-safe report filename."""

    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())

    return normalized or "session"


def normalize_subject_id(value: Any) -> str:
    """Strip generated session timestamp suffixes from subject identifiers."""

    subject_id = required_text(value, "user_id")

    while re.search(r"_\d{10,}$", subject_id):
        subject_id = re.sub(r"_\d{10,}$", "", subject_id)

    return subject_id


def ensure_user(cursor, *, user_id: str) -> None:
    """Create a placeholder subject row when telemetry arrives first."""

    user_id = required_text(user_id, "user_id")

    cursor.execute(
        """
        INSERT INTO users (
            user_id,
            subject_id,
            role,
            is_active,
            notes
        )
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (user_id) DO NOTHING
        """,
        (
            user_id,
            user_id,
            "operator",
            True,
            "Auto-created during research session workflow",
        ),
    )


def resolve_session_configuration(
    cursor,
    *,
    during: dict[str, Any],
    user_id: str,
) -> dict[str, Any]:
    """Validate chamber/protocol selection and normalized pressure metadata."""

    try:
        chamber_id = int(during.get("chamber_id"))
        protocol_id = int(during.get("protocol_id"))
    except (TypeError, ValueError):
        raise ValueError("chamber_id and protocol_id are required") from None

    submitted_actual_ata = number_or_none(
        during.get("actual_ata")
        or during.get("pressure_ata")
        or during.get("ata")
    )
    pressure_input_value = number_or_none(
        during.get("pressure_input_value")
        or during.get("pressure_kpa")
        or during.get("pressure")
    )
    pressure_input_unit = optional_text(
        during.get("pressure_input_unit")
    )

    if pressure_input_unit not in {
        "ata",
        "kpa_gauge",
        "kpa_absolute",
    }:
        raise ValueError("invalid pressure_input_unit")

    if pressure_input_value is None:
        raise ValueError("pressure_input_value is required")

    actual_ata = calculate_pressure_ata(
        pressure_input_value,
        pressure_input_unit,
    )

    if submitted_actual_ata is not None and abs(
        submitted_actual_ata - actual_ata
    ) > 0.01:
        raise ValueError("submitted actual_ata does not match pressure input")

    if not 1.0 <= actual_ata <= 3.0:
        raise ValueError("actual_ata must be between 1.0 and 3.0")

    cursor.execute(
        """
        SELECT
            p.target_ata,
            p.mode,
            p.is_active,
            p.compression_time_min,
            p.exposure_time_min,
            p.decompression_time_min,
            c.max_ata,
            c.is_active,
            p.protocol_version,
            p.organization_id,
            c.organization_id,
            c.location_id,
            u.organization_id,
            u.location_id
        FROM protocols p
        CROSS JOIN chambers c
        CROSS JOIN users u
        WHERE p.protocol_id = %s
          AND c.chamber_id = %s
          AND u.user_id = %s
        LIMIT 1
        """,
        (
            protocol_id,
            chamber_id,
            user_id,
        ),
    )
    config_row = cursor.fetchone()

    if not config_row:
        raise ValueError("selected chamber or protocol does not exist")

    target_ata = number_or_none(config_row[0])
    protocol_mode = config_row[1]
    protocol_active = bool(config_row[2])
    planned_compression = int(config_row[3] or 0)
    planned_exposure = int(config_row[4] or 0)
    planned_decompression = int(config_row[5] or 0)
    chamber_max_ata = float(config_row[6])
    chamber_active = bool(config_row[7])
    protocol_version = int(config_row[8] or 1)
    protocol_organization_id = config_row[9]
    chamber_organization_id = config_row[10]
    chamber_location_id = config_row[11]
    client_organization_id = config_row[12]
    client_location_id = config_row[13]

    if not protocol_active or not chamber_active:
        raise ValueError("selected chamber or protocol is inactive")

    if not (
        protocol_organization_id
        == chamber_organization_id
        == client_organization_id
    ):
        raise ValueError("client, chamber and protocol must belong to one organization")

    if protocol_mode != "wellness":
        raise ValueError("only wellness protocols can be used in this workflow")

    if target_ata is None:
        raise ValueError("selected protocol has no target ATA")

    if target_ata > chamber_max_ata:
        raise ValueError("protocol target exceeds chamber maximum ATA")

    if actual_ata > chamber_max_ata + 0.02:
        raise ValueError("recorded ATA exceeds chamber maximum")

    compression_time_min = positive_int_or_default(
        during.get("compression_time_min"),
        planned_compression,
        allow_zero=True,
    )
    exposure_time_min = positive_int_or_default(
        during.get("exposure_time_min"),
        planned_exposure,
    )
    decompression_time_min = positive_int_or_default(
        during.get("decompression_time_min"),
        planned_decompression,
        allow_zero=True,
    )
    phase_total_duration_min = (
        compression_time_min
        + exposure_time_min
        + decompression_time_min
    )

    program_enrollment_id = optional_positive_int(
        during.get("program_enrollment_id")
    )
    if program_enrollment_id is not None:
        cursor.execute(
            """
            SELECT 1
            FROM client_programs cp
            JOIN wellness_programs wp ON wp.program_id = cp.program_id
            WHERE cp.enrollment_id = %s
              AND cp.client_id = %s
              AND cp.status = 'active'
              AND wp.organization_id = %s
              AND wp.protocol_id = %s
            LIMIT 1
            """,
            (
                program_enrollment_id,
                user_id,
                client_organization_id,
                protocol_id,
            ),
        )
        if not cursor.fetchone():
            raise ValueError("selected program is not active for this client and protocol")

    segments = normalize_session_segments(
        during.get("segments"),
        compression_time_min=compression_time_min,
        exposure_time_min=exposure_time_min,
        decompression_time_min=decompression_time_min,
        target_ata=target_ata,
        actual_ata=actual_ata,
    )
    segmented_total = sum(segment["actual_duration_min"] for segment in segments)
    total_duration_min = (
        segmented_total
        if isinstance(during.get("segments"), list) and during.get("segments")
        else phase_total_duration_min
    )
    if total_duration_min <= 0 or total_duration_min > 360:
        raise ValueError("total session duration must be between 1 and 360 minutes")

    planned_total = (
        planned_compression
        + planned_exposure
        + planned_decompression
    )
    has_deviation = any(
        (
            compression_time_min != planned_compression,
            exposure_time_min != planned_exposure,
            decompression_time_min != planned_decompression,
            abs(actual_ata - target_ata) > 0.02,
        )
    )
    execution_status = optional_text(
        during.get("execution_status")
    ) or ("modified" if has_deviation else "as_planned")
    if execution_status not in {"as_planned", "modified", "interrupted"}:
        raise ValueError("invalid execution_status")
    if has_deviation and execution_status == "as_planned":
        execution_status = "modified"

    deviation_reason = optional_text(during.get("deviation_reason"))
    if execution_status in {"modified", "interrupted"} and not deviation_reason:
        raise ValueError("deviation_reason is required for a modified session")

    return {
        "chamber_id": chamber_id,
        "protocol_id": protocol_id,
        "target_ata": target_ata,
        "actual_ata": actual_ata,
        "pressure_input_value": pressure_input_value,
        "pressure_input_unit": pressure_input_unit,
        "pressure_deviation": round(actual_ata - target_ata, 3),
        "compression_time_min": compression_time_min,
        "exposure_time_min": exposure_time_min,
        "decompression_time_min": decompression_time_min,
        "total_duration_min": total_duration_min,
        "planned_total_duration_min": planned_total,
        "organization_id": client_organization_id,
        "location_id": client_location_id or chamber_location_id,
        "program_enrollment_id": program_enrollment_id,
        "protocol_version": protocol_version,
        "execution_status": execution_status,
        "deviation_reason": deviation_reason,
        "requires_approval": execution_status in {"modified", "interrupted"},
        "segments": segments,
    }


def optional_positive_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError("identifier must be an integer") from None
    if parsed <= 0:
        raise ValueError("identifier must be positive")
    return parsed


def normalize_session_segments(
    value: Any,
    *,
    compression_time_min: int,
    exposure_time_min: int,
    decompression_time_min: int,
    target_ata: float,
    actual_ata: float,
) -> list[dict[str, Any]]:
    """Normalize optional long-session segments or build the standard phases."""

    if not isinstance(value, list) or not value:
        return [
            {
                "sequence_no": 1,
                "phase": "compression",
                "planned_duration_min": compression_time_min,
                "actual_duration_min": compression_time_min,
                "target_ata": target_ata,
                "actual_ata": actual_ata,
                "oxygen_mode": None,
                "note": None,
            },
            {
                "sequence_no": 2,
                "phase": "exposure",
                "planned_duration_min": exposure_time_min,
                "actual_duration_min": exposure_time_min,
                "target_ata": target_ata,
                "actual_ata": actual_ata,
                "oxygen_mode": None,
                "note": None,
            },
            {
                "sequence_no": 3,
                "phase": "decompression",
                "planned_duration_min": decompression_time_min,
                "actual_duration_min": decompression_time_min,
                "target_ata": target_ata,
                "actual_ata": actual_ata,
                "oxygen_mode": None,
                "note": None,
            },
        ]

    allowed_phases = {
        "compression",
        "exposure",
        "air_break",
        "decompression",
        "recovery",
        "other",
    }
    normalized = []
    for index, segment in enumerate(value, start=1):
        if not isinstance(segment, dict):
            raise ValueError("each session segment must be an object")
        phase = optional_text(segment.get("phase"))
        if phase not in allowed_phases:
            raise ValueError("invalid session segment phase")
        duration = positive_int_or_default(
            segment.get("actual_duration_min"),
            0,
            allow_zero=True,
        )
        normalized.append(
            {
                "sequence_no": index,
                "phase": phase,
                "planned_duration_min": optional_positive_int(
                    segment.get("planned_duration_min")
                ),
                "actual_duration_min": duration,
                "target_ata": number_or_none(segment.get("target_ata")) or target_ata,
                "actual_ata": number_or_none(segment.get("actual_ata")) or actual_ata,
                "oxygen_mode": optional_text(segment.get("oxygen_mode")),
                "note": optional_text(segment.get("note")),
            }
        )
    return normalized


def save_session_segments(
    cursor,
    *,
    session_id: str,
    segments: list[dict[str, Any]],
) -> None:
    cursor.execute(
        "DELETE FROM session_segments WHERE session_id = %s",
        (session_id,),
    )
    for segment in segments:
        cursor.execute(
            """
            INSERT INTO session_segments (
                session_id,
                sequence_no,
                phase,
                planned_duration_min,
                actual_duration_min,
                target_ata,
                actual_ata,
                oxygen_mode,
                note
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                session_id,
                segment["sequence_no"],
                segment["phase"],
                segment["planned_duration_min"],
                segment["actual_duration_min"],
                segment["target_ata"],
                segment["actual_ata"],
                segment["oxygen_mode"],
                segment["note"],
            ),
        )


def positive_int_or_default(
    value: Any,
    default: int,
    *,
    allow_zero: bool = False,
) -> int:
    """Normalize a phase duration while preserving protocol defaults."""

    candidate = default if value in (None, "") else value

    try:
        parsed = int(candidate)
    except (TypeError, ValueError):
        raise ValueError("session phase durations must be whole minutes") from None

    minimum = 0 if allow_zero else 1
    if parsed < minimum or parsed > 240:
        raise ValueError("session phase duration is outside the allowed range")

    return parsed


def count_rows(cursor, *, table: str, session_id: str) -> int:
    """Count telemetry rows in one whitelisted session table."""

    allowed_tables = {
        "fit_data",
        "csv_data",
        "merged_data",
    }

    if table not in allowed_tables:
        raise ValueError("invalid table")

    cursor.execute(
        f"""
        SELECT COUNT(*)
        FROM {table}
        WHERE session_id = %s
        """,
        (session_id,),
    )

    return int(cursor.fetchone()[0])


def required_text(value: Any, field_name: str) -> str:
    """Normalize required text fields and reject blanks."""

    normalized = str(value).strip() if value is not None else ""

    if not normalized:
        raise ValueError(f"{field_name} is required")

    return normalized


def optional_text(value: Any) -> str | None:
    """Normalize optional text fields, returning None for blanks."""

    if value is None:
        return None

    normalized = str(value).strip()

    return normalized or None


def number_or_none(value: Any) -> float | None:
    """Convert form/JSON numeric input to float when possible."""

    if value is None or value == "":
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def json_loads(value: Any) -> Any:
    """Decode JSON stored as text, preserving already-decoded values."""

    if value is None:
        return None

    if isinstance(value, (dict, list)):
        return value

    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value
def average_from_payload(
    payload: dict[str, Any],
    field: str,
) -> float | None:
    """Calculate an average from scalar or list telemetry values."""

    value = payload.get(field)

    if value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, list):
        numeric_values = []

        for item in value:
            if isinstance(item, dict):
                item = item.get(field)

            try:
                if item is not None:
                    numeric_values.append(float(item))
            except (TypeError, ValueError):
                continue

        if numeric_values:
            return round(
                sum(numeric_values) / len(numeric_values),
                2,
            )

    return None
