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

from database_postgres import db
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
    user_id = normalize_subject_id(
        optional_text(payload.get("user_id")) or initiated_by or session_id
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
                number_or_none(payload.get("pressure")),
                number_or_none(payload.get("pressure_ata")),
                number_or_none(payload.get("ata")),
                number_or_none(payload.get("oxygen_flow_lpm")),
                number_or_none(payload.get("oxygen_percent")),
                number_or_none(payload.get("temperature")),
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
    user_id = normalize_subject_id(
        required_text(user_id, "user_id")
    )

    connection = db()
    cursor = connection.cursor()

    try:
        ensure_user(cursor, user_id=user_id)

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
                completed
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (session_id)
            DO UPDATE SET
                user_id = EXCLUDED.user_id,
                session_status = EXCLUDED.session_status,
                pre_json = EXCLUDED.pre_json,
                during_json = EXCLUDED.during_json,
                post_json = EXCLUDED.post_json,
                summary = EXCLUDED.summary,
                completed = EXCLUDED.completed
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
            ),
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


def list_research_sessions(
    *,
    requesting_user_id: str | None,
    requesting_role: str,
) -> list[dict[str, Any]]:
    """List sessions visible to the current user role."""

    connection = db()
    cursor = connection.cursor()

    try:
        if requesting_role == "admin":
            cursor.execute(
                """
                SELECT
                    session_id,
                    user_id,
                    session_status,
                    completed,
                    created_at
                FROM full_sessions
                ORDER BY created_at DESC
                """
            )
        else:
            cursor.execute(
                """
                SELECT
                    session_id,
                    user_id,
                    session_status,
                    completed,
                    created_at
                FROM full_sessions
                WHERE user_id = %s
                ORDER BY created_at DESC
                """,
                (requesting_user_id,),
            )

        return [
            {
                "session_id": row[0],
                "user_id": row[1],
                "status": row[2],
                "completed": bool(row[3]),
                "created_at": row[4].isoformat() if row[4] else None,
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
                created_at
            FROM full_sessions
            WHERE session_id = %s
            LIMIT 1
            """,
            (session_id,),
        )

        row = cursor.fetchone()

        if not row:
            return None

        if requesting_role != "admin" and row[1] != requesting_user_id:
            return None

        return {
            "session_id": row[0],
            "user_id": row[1],
            "status": row[2],
            "pre": json_loads(row[3]),
            "during": json_loads(row[4]),
            "post": json_loads(row[5]),
            "summary": json_loads(row[6]),
            "completed": bool(row[7]),
            "created_at": row[8].isoformat() if row[8] else None,
        }

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
) -> Path:
    """Build a PDF report for one authorized session."""

    session = get_research_session(
        session_id=session_id,
        requesting_user_id=requesting_user_id,
        requesting_role=requesting_role,
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
                u.notes
            FROM full_sessions fs
            LEFT JOIN users u
                ON u.user_id = fs.user_id
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

        return {
            **counts,
            "subject": subject,
            "analysis": analysis,
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
                ("Subject ID", session.get("user_id")),
                ("Status", session.get("status")),
                ("Completed", session.get("completed")),
                ("Created at", session.get("created_at")),
            ]
        ),
        Spacer(1, 12),
        Paragraph("Subject", styles["Heading2"]),
        make_table(
            [
                ("Subject ID", (report_data.get("subject") or {}).get("user_id")),
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
        Paragraph("PRE / DURING / POST", styles["Heading2"]),
        make_table(
            [
                ("PRE SpO2", phase_metric(session.get("pre"), "spo2", "avg_spo2")),
                ("PRE pulse / HR", phase_metric(session.get("pre"), "pulse", "hr", "heart_rate")),
                ("PRE HRV", phase_metric(session.get("pre"), "hrv", "rmssd", "avg_hrv")),
                ("PRE check-in", format_context(phase_metric(session.get("pre"), "check_in"))),
                ("DURING avg SpO2", phase_metric(session.get("during"), "avg_spo2", "spo2")),
                ("DURING min SpO2", phase_metric(session.get("during"), "min_spo2")),
                ("DURING avg pulse / HR", phase_metric(session.get("during"), "avg_pulse", "avg_hr", "pulse", "hr")),
                ("DURING avg HRV", phase_metric(session.get("during"), "avg_hrv", "rmssd", "hrv")),
                ("POST SpO2", phase_metric(session.get("post"), "spo2", "avg_spo2")),
                ("POST pulse / HR", phase_metric(session.get("post"), "pulse", "hr", "heart_rate")),
                ("POST HRV", phase_metric(session.get("post"), "hrv", "rmssd", "avg_hrv")),
                ("POST check-out", format_context(phase_metric(session.get("post"), "check_out"))),
            ]
        ),
    ]

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
                    ("Wellness score", analysis.get("overall_score")),
                    ("Load score", analysis.get("stress_score")),
                    ("Oxygenation minimum", analysis.get("hypoxia_score")),
                    (
                        "Heart-rate peak",
                        analysis.get("cardiovascular_score"),
                    ),
                    ("Data quality score", analysis.get("data_quality_score")),
                    ("Data quality warnings", format_list(quality_warnings)),
                    (
                        "Session flagged",
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

    user_id = normalize_subject_id(user_id)

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
