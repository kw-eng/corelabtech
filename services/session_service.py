"""Session persistence and PDF reporting service.

Routes call this module to save PRE/DURING/POST phase data, complete research
sessions, list session ownership safely, delete sessions and generate reports.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
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
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from services.i18n_service import DEFAULT_LOCALE, catalog_for, normalize_locale

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
PRESSURE_OPERATIONAL_TOLERANCE_ATA = 0.05
REPORT_FONT_NAME = "CoreLabTechUnicode"
REPORT_FONT_REGISTERED = False
REPORT_FONT_CANDIDATES = (
    Path("static/fonts/NotoSans-Regular.ttf"),
    Path("static/fonts/DejaVuSans.ttf"),
    Path("C:/Windows/Fonts/arial.ttf"),
    Path("C:/Windows/Fonts/segoeui.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
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
                    fs.actual_ata,
                    ROW_NUMBER() OVER (
                        PARTITION BY fs.user_id
                        ORDER BY fs.created_at ASC, fs.id ASC
                    ),
                    EXISTS (
                        SELECT 1
                        FROM audit_log al
                        WHERE al.action = 'report.export'
                          AND al.entity_type = 'session'
                          AND al.entity_id = fs.session_id
                          AND al.outcome = 'success'
                    ) AS report_exported,
                    (
                        SELECT MAX(al.created_at)
                        FROM audit_log al
                        WHERE al.action = 'report.export'
                          AND al.entity_type = 'session'
                          AND al.entity_id = fs.session_id
                          AND al.outcome = 'success'
                    ) AS report_exported_at
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
                    ,fs.actual_ata,
                    ROW_NUMBER() OVER (
                        PARTITION BY fs.user_id
                        ORDER BY fs.created_at ASC, fs.id ASC
                    ),
                    EXISTS (
                        SELECT 1
                        FROM audit_log al
                        WHERE al.action = 'report.export'
                          AND al.entity_type = 'session'
                          AND al.entity_id = fs.session_id
                          AND al.outcome = 'success'
                    ) AS report_exported,
                    (
                        SELECT MAX(al.created_at)
                        FROM audit_log al
                        WHERE al.action = 'report.export'
                          AND al.entity_type = 'session'
                          AND al.entity_id = fs.session_id
                          AND al.outcome = 'success'
                    ) AS report_exported_at
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
                    fs.actual_ata,
                    ROW_NUMBER() OVER (
                        PARTITION BY fs.user_id
                        ORDER BY fs.created_at ASC, fs.id ASC
                    ),
                    EXISTS (
                        SELECT 1
                        FROM audit_log al
                        WHERE al.action = 'report.export'
                          AND al.entity_type = 'session'
                          AND al.entity_id = fs.session_id
                          AND al.outcome = 'success'
                    ) AS report_exported,
                    (
                        SELECT MAX(al.created_at)
                        FROM audit_log al
                        WHERE al.action = 'report.export'
                          AND al.entity_type = 'session'
                          AND al.entity_id = fs.session_id
                          AND al.outcome = 'success'
                    ) AS report_exported_at
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
                "client_session_number": int(row[7]),
                "report_exported": bool(row[8]),
                "report_exported_at": row[9].isoformat() if row[9] else None,
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


def register_report_font() -> str:
    """Register a Unicode font for PDF output when one is available."""

    global REPORT_FONT_REGISTERED

    if REPORT_FONT_REGISTERED:
        return REPORT_FONT_NAME

    for candidate in REPORT_FONT_CANDIDATES:
        if candidate.exists():
            try:
                pdfmetrics.registerFont(
                    TTFont(REPORT_FONT_NAME, str(candidate))
                )
                REPORT_FONT_REGISTERED = True
                return REPORT_FONT_NAME
            except Exception:
                continue

    return "Helvetica"


def make_report_styles():
    """Create ReportLab styles with a Unicode-capable base font."""

    font_name = register_report_font()
    styles = getSampleStyleSheet()

    for style_name in (
        "Normal",
        "BodyText",
        "Title",
        "Heading1",
        "Heading2",
    ):
        if style_name in styles:
            styles[style_name].fontName = font_name

    return styles


def report_catalog(locale: str | None) -> dict[str, str]:
    """Return report translations for one locale with English fallback."""

    return catalog_for(normalize_locale(locale or DEFAULT_LOCALE))


def report_text(catalog: dict[str, str], key: str, **params: Any) -> str:
    """Translate one report label with optional format params."""

    text = catalog.get(key) or catalog_for(DEFAULT_LOCALE).get(key) or key

    if params:
        try:
            return text.format(**params)
        except (KeyError, ValueError):
            return text

    return text


def generate_session_report(
    *,
    session_id: str,
    requesting_user_id: str | None,
    requesting_role: str,
    requesting_organization_id: int | None = None,
    locale: str | None = None,
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
        locale=locale,
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
                ),
                (
                    SELECT COUNT(*)
                    FROM full_sessions client_fs
                    WHERE client_fs.user_id = fs.user_id
                      AND client_fs.session_id NOT LIKE
                          'PIPELINE_VALIDATION_%%'
                      AND (
                          client_fs.created_at < fs.created_at
                          OR (
                              client_fs.created_at = fs.created_at
                              AND client_fs.id <= fs.id
                          )
                      )
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
                "client_session_number": subject_row[27],
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
    locale: str | None = None,
) -> None:
    """Render a concise, client-facing wellness session report."""

    catalog = report_catalog(locale)
    styles = make_report_styles()
    styles.add(
        ParagraphStyle(
            name="BrandTitle",
            parent=styles["Title"],
            alignment=0,
            fontSize=18,
            leading=21,
            textColor=colors.HexColor("#0b8f7f"),
            spaceAfter=0,
        )
    )
    styles.add(
        ParagraphStyle(
            name="BrandSubtitle",
            parent=styles["BodyText"],
            alignment=0,
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#64748b"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="ReportTitle",
            parent=styles["Heading1"],
            alignment=2,
            fontSize=17,
            leading=20,
            textColor=colors.HexColor("#13283a"),
            spaceAfter=0,
        )
    )
    styles.add(
        ParagraphStyle(
            name="ReportSection",
            parent=styles["Heading2"],
            fontSize=11.5,
            leading=14,
            textColor=colors.HexColor("#13283a"),
            spaceBefore=9,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            name="MetricLabel",
            parent=styles["BodyText"],
            alignment=TA_CENTER,
            fontSize=7.5,
            leading=9,
            textColor=colors.HexColor("#64748b"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="MetricValue",
            parent=styles["Heading2"],
            alignment=TA_CENTER,
            fontSize=15,
            leading=18,
            textColor=colors.HexColor("#0f766e"),
            spaceAfter=0,
        )
    )
    styles.add(
        ParagraphStyle(
            name="NoticeText",
            parent=styles["BodyText"],
            fontSize=8,
            leading=10.5,
            textColor=colors.HexColor("#64748b"),
        )
    )

    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        title=f"CoreLabTech wellness report {session['session_id']}",
        author="CoreLabTech",
        subject=report_text(catalog, "report.wellness_session"),
        leftMargin=17 * mm,
        rightMargin=17 * mm,
        topMargin=14 * mm,
        bottomMargin=18 * mm,
    )

    session_config = report_data.get("session_config") or {}
    subject = report_data.get("subject") or {}
    analysis = report_data.get("analysis") or {}
    analysis_result = analysis.get("result") or {}
    wellness_flags = analysis_result.get("wellness_flags") or {}
    features = analysis.get("features") or {}
    wellness_history = report_data.get("wellness_history") or {}
    baseline = wellness_history.get("baseline") or {}
    quality_warnings = analysis_result.get("quality_warnings") or []
    client_session_number = session_config.get("client_session_number") or "-"
    program_name = session_config.get("program_name") or "Single session"
    program_progress = (
        f"{session_config.get('program_completed_sessions')} of "
        f"{session_config.get('program_total_sessions')}"
        if session_config.get("program_name")
        else "Not enrolled"
    )
    synchronized_samples = int(report_data.get("merged_samples") or 0)
    source_samples = max(
        int(report_data.get("fit_samples") or 0),
        int(report_data.get("csv_samples") or 0),
    )
    missing_samples = (
        max(0, source_samples - synchronized_samples)
        if source_samples
        else None
    )

    story = [
        make_report_header(
            session=session,
            report_data=report_data,
            styles=styles,
            catalog=catalog,
        ),
        Spacer(1, 12),
        make_metric_strip(
            [
                (
                    report_text(catalog, "report.metric_wellness_response"),
                    format_score(analysis.get("overall_score")),
                ),
                (
                    report_text(catalog, "report.metric_data_quality"),
                    format_score(analysis.get("data_quality_score")),
                ),
                (
                    report_text(catalog, "report.metric_sync_quality"),
                    format_percent(features.get("match_rate")),
                ),
                (
                    report_text(catalog, "report.metric_spo2_minimum"),
                    format_measurement(analysis.get("hypoxia_score"), "%", 1),
                ),
            ],
            styles,
        ),
        Spacer(1, 8),
        KeepTogether(
            [
                Paragraph(
                    report_text(catalog, "report.session_overview"),
                    styles["ReportSection"],
                ),
                make_table(
                    [
                        ("Client", subject.get("user_id")),
                        (
                            report_text(catalog, "report.client_session"),
                            f"Session {client_session_number}",
                        ),
                        ("Date", format_report_datetime(session.get("created_at"))),
                        ("Program", f"{program_name} - {program_progress}"),
                        ("Protocol", session.get("protocol_name")),
                        (
                            "Location",
                            " / ".join(
                                value
                                for value in (
                                    session_config.get("location_name"),
                                    session.get("chamber_name"),
                                )
                                if value
                            ),
                        ),
                        (
                            "Pressure",
                            (
                                f"{format_measurement(session.get('actual_ata'), ' ATA', 2)} "
                                f"(target {format_measurement(session.get('target_ata'), ' ATA', 2)})"
                            ),
                        ),
                        (
                            "Duration",
                            format_measurement(
                                session.get("total_duration_min"),
                                " min",
                                0,
                            ),
                        ),
                        (
                            report_text(catalog, "report.session_status"),
                            format_report_status(
                                session.get("execution_status")
                                or session.get("status")
                            ),
                        ),
                    ]
                ),
            ]
        ),
    ]

    if analysis:
        story.extend(
            [
                KeepTogether(
                    [
                        Paragraph(
                            report_text(
                                catalog,
                                "report.wellness_interpretation",
                            ),
                            styles["ReportSection"],
                        ),
                        Spacer(1, 2),
                        Paragraph(
                            escape_text(analysis.get("summary")),
                            styles["BodyText"],
                        ),
                    ]
                ),
                KeepTogether(
                    [
                        Paragraph(
                            report_text(catalog, "report.operator_review"),
                            styles["ReportSection"],
                        ),
                        Spacer(1, 2),
                        Paragraph(
                            escape_text(analysis.get("recommendations")),
                            styles["BodyText"],
                        ),
                    ]
                ),
            ]
        )
    else:
        story.extend(
            [
                Paragraph(
                    report_text(catalog, "report.wellness_interpretation"),
                    styles["ReportSection"],
                ),
                Paragraph(
                    report_text(catalog, "report.no_analysis"),
                    styles["BodyText"],
                ),
            ]
        )

    story.append(
        KeepTogether(
            [
                Paragraph(
                    report_text(catalog, "report.session_data_quality"),
                    styles["ReportSection"],
                ),
                make_table(
                    [
                        (
                            "Data quality score",
                            format_score(analysis.get("data_quality_score")),
                        ),
                        (
                            "Coverage",
                            format_percent(features.get("coverage_percent")),
                        ),
                        (
                            "Synchronization quality",
                            format_percent(features.get("match_rate")),
                        ),
                        ("Missing samples", missing_samples),
                        (
                            "HR / pulse alignment",
                            (
                                "Operator review recommended"
                                if wellness_flags.get(
                                    "sensor_alignment_warning"
                                )
                                else "No alignment warning"
                            ),
                        ),
                        (
                            "SpO2 range",
                            (
                                "Operator review recommended"
                                if wellness_flags.get("oxygenation_drop")
                                else "No range warning"
                            ),
                        ),
                        (
                            "Quality notes",
                            format_warning_list(quality_warnings),
                        ),
                    ]
                ),
                Spacer(1, 5),
                Paragraph(
                    report_text(catalog, "report.confidence_note"),
                    styles["NoticeText"],
                ),
            ]
        )
    )

    story.extend(
        [
            PageBreak(),
            make_page_header(
                report_text(catalog, "report.session_details"),
                styles,
            ),
            Spacer(1, 6),
            KeepTogether(
                [
                    Paragraph(
                        report_text(catalog, "report.session_timeline"),
                        styles["ReportSection"],
                    ),
                    make_table(
                        [
                            (
                                f"{segment.get('sequence_no')}. "
                                f"{str(segment.get('phase') or '').replace('_', ' ').title()}",
                                (
                                    f"{format_measurement(segment.get('actual_duration_min'), ' min', 0)}"
                                    f" at {format_measurement(segment.get('actual_ata'), ' ATA', 2)}"
                                    + (
                                        f" - {segment.get('note')}"
                                        if segment.get("note")
                                        else ""
                                    )
                                ),
                            )
                            for segment in session.get("segments") or []
                        ]
                        or [("Timeline", "No segment data available")]
                    ),
                ]
            ),
            KeepTogether(
                [
                    Paragraph(
                        "Check-in and Recovery",
                        styles["ReportSection"],
                    ),
                    make_comparison_table(
                        [
                            (
                                "SpO2",
                                format_measurement(
                                    phase_metric(
                                        session.get("pre"),
                                        "spo2",
                                        "avg_spo2",
                                    ),
                                    "%",
                                    0,
                                ),
                                format_measurement(
                                    phase_metric(
                                        session.get("post"),
                                        "spo2",
                                        "avg_spo2",
                                    ),
                                    "%",
                                    0,
                                ),
                            ),
                            (
                                "Pulse / HR",
                                format_measurement(
                                    phase_metric(
                                        session.get("pre"),
                                        "pulse",
                                        "hr",
                                        "heart_rate",
                                    ),
                                    " bpm",
                                    0,
                                ),
                                format_measurement(
                                    phase_metric(
                                        session.get("post"),
                                        "pulse",
                                        "hr",
                                        "heart_rate",
                                    ),
                                    " bpm",
                                    0,
                                ),
                            ),
                            (
                                "HRV",
                                format_measurement(
                                    phase_metric(
                                        session.get("pre"),
                                        "hrv",
                                        "rmssd",
                                        "avg_hrv",
                                    ),
                                    " ms",
                                    1,
                                ),
                                format_measurement(
                                    phase_metric(
                                        session.get("post"),
                                        "hrv",
                                        "rmssd",
                                        "avg_hrv",
                                    ),
                                    " ms",
                                    1,
                                ),
                            ),
                        ]
                    ),
                    Spacer(1, 5),
                    Paragraph(
                        "<b>Check-in context:</b> "
                        + escape_text(
                            format_context(
                                phase_metric(
                                    session.get("pre"),
                                    "check_in",
                                )
                            )
                        ),
                        styles["NoticeText"],
                    ),
                    Paragraph(
                        "<b>Recovery context:</b> "
                        + escape_text(
                            format_context(
                                phase_metric(
                                    session.get("post"),
                                    "check_out",
                                )
                            )
                        ),
                        styles["NoticeText"],
                    ),
                ]
            ),
            KeepTogether(
                [
                    Paragraph(
                        report_text(catalog, "report.session_environment"),
                        styles["ReportSection"],
                    ),
                    make_table(
                        [
                            (
                                "Oxygen flow",
                                format_measurement(
                                    phase_metric(
                                        session.get("during"),
                                        "oxygen_flow_lpm",
                                    ),
                                    " L/min",
                                    1,
                                ),
                            ),
                            (
                                "Estimated mask O2",
                                format_measurement(
                                    phase_metric(
                                        session.get("during"),
                                        "oxygen_mask_percent",
                                        "oxygen_percent",
                                    ),
                                    "%",
                                    1,
                                ),
                            ),
                            (
                                "Chamber temperature",
                                format_measurement(
                                    phase_metric(
                                        session.get("during"),
                                        "chamber_temperature",
                                        "temperature",
                                    ),
                                    " C",
                                    1,
                                ),
                            ),
                            (
                                "Pressure deviation",
                                format_measurement(
                                    session.get("pressure_deviation"),
                                    " ATA",
                                    3,
                                ),
                            ),
                        ]
                    ),
                ]
            ),
            KeepTogether(
                [
                    Paragraph(
                        report_text(catalog, "report.data_sources"),
                        styles["ReportSection"],
                    ),
                    make_table(
                        [
                            (
                                "HR / HRV samples",
                                report_data.get("fit_samples"),
                            ),
                            (
                                "SpO2 / pulse samples",
                                report_data.get("csv_samples"),
                            ),
                            (
                                "Synchronized samples",
                                report_data.get("merged_samples"),
                            ),
                        ]
                    ),
                ]
            ),
            KeepTogether(
                [
                    Paragraph(
                        report_text(catalog, "report.personal_baseline"),
                        styles["ReportSection"],
                    ),
                    make_table(
                        [
                            (
                                "Baseline status",
                                format_report_status(
                                    wellness_history.get(
                                        "baseline_confidence"
                                    )
                                ),
                            ),
                            (
                                "Sessions in last 30 days",
                                wellness_history.get("unique_sessions_30d"),
                            ),
                            (
                                "RMSSD - 7 days",
                                format_measurement(
                                    baseline.get("rmssd_7d"),
                                    " ms",
                                    1,
                                ),
                            ),
                            (
                                "SpO2 average",
                                format_measurement(
                                    baseline.get("spo2_avg"),
                                    "%",
                                    1,
                                ),
                            ),
                            (
                                "SpO2 minimum",
                                format_measurement(
                                    baseline.get("spo2_min"),
                                    "%",
                                    1,
                                ),
                            ),
                            (
                                "Baseline data quality",
                                format_score(
                                    baseline.get("data_quality_score")
                                ),
                            ),
                        ]
                    ),
                ]
            ),
            Spacer(1, 4),
            Paragraph(
                "<b>" + escape_text(report_text(catalog, "report.wellness_notice")) + "</b>",
                styles["NoticeText"],
            ),
        ]
    )

    doc.build(
        story,
        onFirstPage=lambda canvas, doc: draw_report_footer(
            canvas,
            doc,
            catalog=catalog,
        ),
        onLaterPages=lambda canvas, doc: draw_report_footer(
            canvas,
            doc,
            catalog=catalog,
        ),
    )


def build_series_pdf_report(
    *,
    path: Path,
    series_data: dict[str, Any],
    locale: str | None = None,
) -> None:
    """Render a concise wellness series report for one client."""

    catalog = report_catalog(locale)
    styles = make_report_styles()
    styles.add(
        ParagraphStyle(
            name="BrandTitle",
            parent=styles["Title"],
            alignment=0,
            fontSize=18,
            leading=21,
            textColor=colors.HexColor("#0b8f7f"),
            spaceAfter=0,
        )
    )
    styles.add(
        ParagraphStyle(
            name="BrandSubtitle",
            parent=styles["BodyText"],
            alignment=0,
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#64748b"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="ReportTitle",
            parent=styles["Heading1"],
            alignment=2,
            fontSize=17,
            leading=20,
            textColor=colors.HexColor("#13283a"),
            spaceAfter=0,
        )
    )
    styles.add(
        ParagraphStyle(
            name="ReportSection",
            parent=styles["Heading2"],
            fontSize=11.5,
            leading=14,
            textColor=colors.HexColor("#13283a"),
            spaceBefore=9,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            name="MetricLabel",
            parent=styles["BodyText"],
            alignment=TA_CENTER,
            fontSize=7.5,
            leading=9,
            textColor=colors.HexColor("#64748b"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="MetricValue",
            parent=styles["Heading2"],
            alignment=TA_CENTER,
            fontSize=15,
            leading=18,
            textColor=colors.HexColor("#0f766e"),
            spaceAfter=0,
        )
    )
    styles.add(
        ParagraphStyle(
            name="NoticeText",
            parent=styles["BodyText"],
            fontSize=8,
            leading=10.5,
            textColor=colors.HexColor("#64748b"),
        )
    )

    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        title=f"CoreLabTech wellness series report {series_data.get('user_id')}",
        author="CoreLabTech",
        subject=report_text(catalog, "report.wellness_series"),
        leftMargin=17 * mm,
        rightMargin=17 * mm,
        topMargin=14 * mm,
        bottomMargin=18 * mm,
    )

    analyses = series_data.get("analyses") or []
    comparison = series_data.get("first_last_comparison") or {}
    quality_engine = series_data.get("data_quality_engine") or {}
    protocol = series_data.get("protocol") or {}
    warnings = quality_engine.get("warning_counts") or {}
    warning_summary = (
        ", ".join(
            f"{str(key).replace('_', ' ').title()}: {value}"
            for key, value in warnings.items()
        )
        if warnings
        else "No repeated quality warnings"
    )
    latest_session = analyses[-1] if analyses else {}
    flagged_sessions = series_data.get(
        "flagged_session_count",
        series_data.get("anomaly_count", 0),
    )

    header = Table(
        [
            [
                Paragraph(
                    report_text(catalog, "report.corelabtech"),
                    styles["BrandTitle"],
                ),
                Paragraph(
                    report_text(catalog, "report.wellness_series"),
                    styles["ReportTitle"],
                ),
            ],
            [
                Paragraph(
                    report_text(catalog, "report.platform"),
                    styles["BrandSubtitle"],
                ),
                Paragraph(
                    (
                        f"Client {escape_text(series_data.get('user_id'))}"
                        f" &nbsp; | &nbsp; Last {escape_text(series_data.get('series_limit'))}"
                    ),
                    ParagraphStyle(
                        "SeriesHeaderMeta",
                        parent=styles["BrandSubtitle"],
                        alignment=2,
                    ),
                ),
            ],
        ],
        colWidths=[240, 240],
    )
    header.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("LINEBELOW", (0, 1), (-1, 1), 1.5, colors.HexColor("#14b8a6")),
                ("LEFTPADDING", (0, 0), (0, -1), 0),
                ("RIGHTPADDING", (1, 0), (1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 1),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 7),
                ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
            ]
        )
    )

    story = [
        header,
        Spacer(1, 12),
        make_metric_strip(
            [
                (
                    report_text(catalog, "report.metric_analyzed"),
                    series_data.get("records", 0),
                ),
                (
                    report_text(catalog, "report.metric_trend"),
                    str(series_data.get("trend_direction") or "-").title(),
                ),
                (
                    report_text(catalog, "report.metric_avg_score"),
                    format_score(series_data.get("avg_score")),
                ),
                (
                    report_text(catalog, "report.metric_data_quality"),
                    format_score(series_data.get("avg_data_quality")),
                ),
            ],
            styles,
        ),
        Spacer(1, 8),
        KeepTogether(
            [
                Paragraph(
                    report_text(catalog, "report.series_overview"),
                    styles["ReportSection"],
                ),
                make_table(
                    [
                        ("Client", series_data.get("user_id")),
                        ("Range", f"Last {series_data.get('series_limit')} sessions"),
                        ("Protocol", protocol.get("name") or protocol.get("code")),
                        ("Total sessions", series_data.get("session_count")),
                        ("Analyzed sessions", series_data.get("records")),
                        ("Review flags", flagged_sessions),
                        (
                            "Latest session",
                            latest_session.get("session_id") or "-",
                        ),
                        (
                            "Latest score",
                            format_score(series_data.get("latest_score")),
                        ),
                    ]
                ),
            ]
        ),
        KeepTogether(
            [
                Paragraph(
                    report_text(catalog, "report.series_interpretation"),
                    styles["ReportSection"],
                ),
                Paragraph(
                    escape_text(
                        series_data.get("wellness_interpretation")
                        or "Interpret the trend together with session data quality.",
                    ),
                    styles["BodyText"],
                ),
            ]
        ),
        KeepTogether(
            [
                Paragraph(
                    report_text(catalog, "report.first_last"),
                    styles["ReportSection"],
                ),
                make_table(
                    [
                        (
                            "Wellness score",
                            (
                                f"{format_score(comparison.get('first_avg_score'))}"
                                f" -> {format_score(comparison.get('last_avg_score'))}"
                                f" ({format_delta_text(comparison.get('score_delta'))})"
                            ),
                        ),
                        (
                            "Data quality",
                            (
                                f"{format_score(comparison.get('first_avg_data_quality'))}"
                                f" -> {format_score(comparison.get('last_avg_data_quality'))}"
                                f" ({format_delta_text(comparison.get('data_quality_delta'))})"
                            ),
                        ),
                    ]
                ),
            ]
        ),
        KeepTogether(
            [
                Paragraph(
                    report_text(catalog, "report.data_quality_engine"),
                    styles["ReportSection"],
                ),
                make_table(
                    [
                        ("Average coverage", format_percent(series_data.get("avg_coverage"))),
                        ("Average sync quality", format_percent(series_data.get("avg_match_rate"))),
                        ("Missing samples", quality_engine.get("total_missing_samples")),
                        ("Sensor gap sessions", quality_engine.get("sensor_gap_sessions")),
                        (
                            "HR / pulse mismatch",
                            quality_engine.get("hr_pulse_mismatch_sessions"),
                        ),
                        (
                            "SpO2 warnings",
                            quality_engine.get("spo2_warning_sessions"),
                        ),
                        ("Warning summary", warning_summary),
                    ]
                ),
                Spacer(1, 5),
                Paragraph(
                    escape_text(
                        quality_engine.get("explanation")
                        or "Data quality describes confidence in session data, not client health.",
                    ),
                    styles["NoticeText"],
                ),
            ]
        ),
        PageBreak(),
        make_page_header(
            report_text(catalog, "report.series_table"),
            styles,
        ),
        Spacer(1, 6),
        make_series_session_table(analyses, styles, catalog=catalog),
        Spacer(1, 8),
        Paragraph(
            "<b>" + escape_text(report_text(catalog, "report.series_notice")) + "</b>",
            styles["NoticeText"],
        ),
    ]

    doc.build(
        story,
        onFirstPage=lambda canvas, doc: draw_report_footer(
            canvas,
            doc,
            catalog=catalog,
        ),
        onLaterPages=lambda canvas, doc: draw_report_footer(
            canvas,
            doc,
            catalog=catalog,
        ),
    )


def make_report_header(
    *,
    session: dict[str, Any],
    report_data: dict[str, Any],
    styles,
    catalog: dict[str, str],
) -> Table:
    """Create a light, restrained report header."""

    session_config = report_data.get("session_config") or {}
    session_number = session_config.get("client_session_number") or "-"

    header = Table(
        [
            [
                Paragraph(
                    report_text(catalog, "report.corelabtech"),
                    styles["BrandTitle"],
                ),
                Paragraph(
                    report_text(catalog, "report.wellness_session"),
                    styles["ReportTitle"],
                ),
            ],
            [
                Paragraph(
                    report_text(catalog, "report.platform"),
                    styles["BrandSubtitle"],
                ),
                Paragraph(
                    f"Session {escape_text(session_number)}"
                    f" &nbsp; | &nbsp; "
                    f"{escape_text(format_report_datetime(session.get('created_at')))}",
                    ParagraphStyle(
                        "HeaderMeta",
                        parent=styles["BrandSubtitle"],
                        alignment=2,
                    ),
                )
            ],
        ],
        colWidths=[240, 240],
    )
    header.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("LINEBELOW", (0, 1), (-1, 1), 1.5, colors.HexColor("#14b8a6")),
                ("LEFTPADDING", (0, 0), (0, -1), 0),
                ("RIGHTPADDING", (1, 0), (1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 1),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 7),
                ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
            ]
        )
    )

    return header


def make_metric_strip(
    metrics: list[tuple[str, Any]],
    styles,
) -> Table:
    """Create a compact strip of headline session metrics."""

    cells = [
        [
            Paragraph(escape_text(label), styles["MetricLabel"]),
            Spacer(1, 3),
            Paragraph(escape_text(value), styles["MetricValue"]),
        ]
        for label, value in metrics
    ]
    table = Table([cells], colWidths=[120] * len(cells))
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f4faf9")),
                ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#c9e6e1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c9e6e1")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
            ]
        )
    )
    return table


def make_page_header(title: str, styles) -> Table:
    """Create a restrained continuation header for later report pages."""

    table = Table(
        [
            [
                Paragraph("CoreLabTech", styles["BrandTitle"]),
                Paragraph(escape_text(title), styles["ReportTitle"]),
            ]
        ],
        colWidths=[240, 240],
    )
    table.setStyle(
        TableStyle(
            [
                ("LINEBELOW", (0, 0), (-1, -1), 1.5, colors.HexColor("#14b8a6")),
                ("LEFTPADDING", (0, 0), (0, 0), 0),
                ("RIGHTPADDING", (1, 0), (1, 0), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
            ]
        )
    )
    return table


def make_comparison_table(rows: list[tuple[str, Any, Any]]) -> Table:
    """Create a check-in versus recovery comparison table."""

    body_style = getSampleStyleSheet()["BodyText"]
    body_style.fontName = register_report_font()
    header_style = ParagraphStyle(
        "ComparisonHeader",
        parent=body_style,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#475569"),
    )
    table_data = [
        [
            Paragraph("METRIC", header_style),
            Paragraph("CHECK-IN", header_style),
            Paragraph("RECOVERY", header_style),
        ],
        *[
            [
                Paragraph(escape_text(label), body_style),
                Paragraph(escape_text(check_in), body_style),
                Paragraph(escape_text(recovery), body_style),
            ]
            for label, check_in, recovery in rows
        ],
    ]
    table = Table(table_data, colWidths=[180, 150, 150])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e9f5f3")),
                ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#d6dee5")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def make_series_session_table(
    analyses: list[dict[str, Any]],
    styles,
    *,
    catalog: dict[str, str],
) -> Table:
    """Create a compact table of analyzed sessions for the series report."""

    body_style = ParagraphStyle(
        "SeriesTableBody",
        parent=getSampleStyleSheet()["BodyText"],
        fontName=register_report_font(),
        fontSize=7.4,
        leading=9,
    )
    header_style = ParagraphStyle(
        "SeriesTableHeader",
        parent=body_style,
        fontSize=7,
        leading=8,
        textColor=colors.HexColor("#475569"),
    )
    rows = [
        [
            Paragraph(report_text(catalog, "report.table_session"), header_style),
            Paragraph(report_text(catalog, "report.table_date"), header_style),
            Paragraph(report_text(catalog, "report.table_score"), header_style),
            Paragraph(report_text(catalog, "report.table_quality"), header_style),
            Paragraph(report_text(catalog, "report.table_sync"), header_style),
            Paragraph("SPO2", header_style),
            Paragraph(report_text(catalog, "report.table_pulse"), header_style),
            Paragraph(report_text(catalog, "report.table_review"), header_style),
        ]
    ]

    for row in analyses:
        rows.append(
            [
                Paragraph(escape_text(row.get("session_id")), body_style),
                Paragraph(escape_text(format_report_datetime(row.get("created_at"))), body_style),
                Paragraph(escape_text(format_score(row.get("overall_score"))), body_style),
                Paragraph(escape_text(format_score(row.get("data_quality_score"))), body_style),
                Paragraph(escape_text(format_percent(row.get("match_rate"))), body_style),
                Paragraph(escape_text(format_measurement(row.get("avg_spo2"), "%", 1)), body_style),
                Paragraph(escape_text(format_measurement(row.get("avg_pulse"), " bpm", 0)), body_style),
                Paragraph(
                    (
                        report_text(catalog, "report.review_required")
                        if row.get("session_flagged")
                        or row.get("quality_warning_count")
                        else report_text(catalog, "report.review_ok")
                    ),
                    body_style,
                ),
            ]
        )

    if len(rows) == 1:
        rows.append(
            [
                Paragraph("-", body_style),
                Paragraph("-", body_style),
                Paragraph("-", body_style),
                Paragraph("-", body_style),
                Paragraph("-", body_style),
                Paragraph("-", body_style),
                Paragraph("-", body_style),
                Paragraph(
                    report_text(catalog, "report.no_analyzed_sessions"),
                    body_style,
                ),
            ]
        )

    table = Table(
        rows,
        colWidths=[92, 72, 56, 58, 48, 44, 48, 62],
        repeatRows=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e9f5f3")),
                ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#d6dee5")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def draw_report_footer(canvas, doc, *, catalog: dict[str, str]) -> None:
    """Draw a consistent footer on each generated report page."""

    canvas.saveState()
    width, _ = A4
    canvas.setStrokeColor(colors.HexColor("#c9ced6"))
    canvas.setLineWidth(0.25)
    canvas.line(17 * mm, 14 * mm, width - 17 * mm, 14 * mm)
    canvas.setFont(register_report_font(), 7)
    canvas.setFillColor(colors.HexColor("#4f6475"))
    canvas.drawString(
        17 * mm,
        9 * mm,
        report_text(catalog, "report.footer_notice"),
    )
    canvas.drawRightString(
        width - 17 * mm,
        9 * mm,
        f"Page {doc.page}",
    )
    canvas.restoreState()


def make_table(rows: list[tuple[str, Any]]) -> Table:
    """Create a consistently styled two-column report table."""

    body_style = getSampleStyleSheet()["BodyText"]
    body_style.fontName = register_report_font()
    table = Table(
        [
            [
                Paragraph(str(label), body_style),
                Paragraph(escape_text(value), body_style),
            ]
            for label, value in rows
        ],
        colWidths=[150, 330],
    )

    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f4f7f9")),
                ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#d6dee5")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 5.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5.5),
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


def format_score(value: Any) -> str:
    """Format a normalized report score on a 100-point scale."""

    measurement = format_measurement(value, "", 1)
    return f"{measurement} / 100" if measurement != "-" else "-"


def format_delta_text(value: Any) -> str:
    """Format score deltas with an explicit sign."""

    if value in (None, ""):
        return "-"

    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)

    sign = "+" if numeric >= 0 else ""
    return f"{sign}{format_measurement(numeric, '', 1)}"


def format_percent(value: Any) -> str:
    """Format percentage values for PDF metrics."""

    return format_measurement(value, "%", 1)


def format_measurement(
    value: Any,
    suffix: str = "",
    decimals: int = 1,
) -> str:
    """Format report measurements without exposing database precision."""

    if value in (None, ""):
        return "-"

    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return f"{value}{suffix}"

    text = f"{numeric:.{decimals}f}"
    if decimals:
        text = text.rstrip("0").rstrip(".")

    return f"{text}{suffix}"


def format_report_datetime(value: Any) -> str:
    """Format ISO timestamps for a human-facing report."""

    if value in (None, ""):
        return "-"

    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return str(value)

    return parsed.strftime("%d %b %Y, %H:%M")


def format_report_status(value: Any) -> str:
    """Convert internal enum values into readable status labels."""

    if value in (None, ""):
        return "-"

    labels = {
        "active": "Active",
        "as_planned": "Completed as planned",
        "baseline": "Baseline building",
        "collecting": "Baseline building",
        "completed": "Completed",
        "modified": "Completed with changes",
        "paused": "Paused",
        "cancelled": "Cancelled",
    }
    key = str(value).strip().lower()
    return labels.get(key, key.replace("_", " ").title())


def format_warning_list(values: Any) -> str:
    """Translate internal quality warning codes for report readers."""

    labels = {
        "sensor_alignment_warning": "HR / pulse alignment requires review",
        "low_coverage": "Low sensor coverage",
        "sync_quality_warning": "Synchronization quality requires review",
        "spo2_range_warning": "SpO2 range requires review",
    }

    if not values:
        return "No quality warnings"

    if not isinstance(values, (list, tuple, set)):
        values = [values]

    return "; ".join(
        labels.get(str(value), str(value).replace("_", " ").title())
        for value in values
    )


def format_context(value: Any) -> str:
    """Format optional check-in/check-out context for the PDF."""

    if not isinstance(value, dict):
        return "-"

    pairs = []
    for key, item in value.items():
        if item in (None, ""):
            continue

        label = key.replace("_", " ").title()
        if isinstance(item, bool):
            item = "Yes" if item else "No"
        pairs.append(f"{label}: {item}")

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

    if actual_ata > chamber_max_ata + PRESSURE_OPERATIONAL_TOLERANCE_ATA:
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
            abs(actual_ata - target_ata) > PRESSURE_OPERATIONAL_TOLERANCE_ATA,
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
