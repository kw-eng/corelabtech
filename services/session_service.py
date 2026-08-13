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
from reportlab.graphics.shapes import Drawing, Line, String
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
from services.llm_narration import build_session_fact_sheet
from services.research_summary import build_research_summary
from services.session_response_presentation import build_localized_session_response
from services.customer_wellness_insight import (
    build_series_customer_insight,
    build_session_customer_insight,
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
    limit: int = 100,
) -> list[dict[str, Any]]:
    """List sessions visible to the current user role."""

    limit = max(1, min(int(limit), 200))

    connection = db()
    cursor = connection.cursor()

    try:
        scope_clause = "fs.session_id NOT LIKE 'PIPELINE_VALIDATION_%%'"
        params: list[Any] = []
        if requesting_role in CLIENT_STAFF_ROLES:
            scope_clause += " AND fs.organization_id = %s"
            params.append(requesting_organization_id)
        elif requesting_role != "admin":
            scope_clause += " AND fs.user_id = %s"
            params.append(requesting_user_id)

        # Audit export metadata used to be obtained with two correlated lookups
        # per session.  On a growing audit_log that turns the startup list into
        # an N+1 query.  Aggregate only the visible session ids once instead.
        cursor.execute(
            f"""
            WITH scoped_sessions AS (
                SELECT
                    fs.session_id, fs.user_id, fs.session_status, fs.completed,
                    fs.created_at, p.name AS protocol_name, fs.actual_ata,
                    ROW_NUMBER() OVER (
                        PARTITION BY fs.user_id
                        ORDER BY fs.created_at ASC, fs.id ASC
                    ) AS client_session_number
                FROM full_sessions fs
                LEFT JOIN protocols p ON p.protocol_id = fs.protocol_id
                WHERE {scope_clause}
            ), listed_sessions AS (
                SELECT * FROM scoped_sessions
                ORDER BY created_at DESC
                LIMIT %s
            ), report_exports AS (
                SELECT al.entity_id, MAX(al.created_at) AS exported_at
                FROM audit_log al
                JOIN listed_sessions ls ON ls.session_id = al.entity_id
                WHERE al.action = 'report.export'
                  AND al.entity_type = 'session'
                  AND al.outcome = 'success'
                GROUP BY al.entity_id
            )
            SELECT
                ls.session_id, ls.user_id, ls.session_status, ls.completed,
                ls.created_at, ls.protocol_name, ls.actual_ata,
                ls.client_session_number,
                report_exports.entity_id IS NOT NULL AS report_exported,
                report_exports.exported_at AS report_exported_at
            FROM listed_sessions ls
            LEFT JOIN report_exports ON report_exports.entity_id = ls.session_id
            ORDER BY ls.created_at DESC
            """,
            tuple([*params, limit]),
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


def localized_count(catalog: dict[str, str], value: Any, noun: str) -> str:
    """Format the few Polish count forms used in customer report prose."""

    try:
        count = int(value)
    except (TypeError, ValueError):
        count = 0
    if noun == "session":
        forms = ("sesja", "sesje", "sesji")
    elif noun == "warning":
        forms = ("ostrzeżenie", "ostrzeżenia", "ostrzeżeń")
    else:
        return str(count)
    is_polish = catalog.get("report.label_client") == "Klient"
    if not is_polish:
        return f"{count} {noun}{'' if count == 1 else 's'}"
    form = forms[0] if count == 1 else forms[1] if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14 else forms[2]
    return f"{count} {form}"


def localized_series_comparison(catalog: dict[str, str], comparison: dict[str, Any]) -> str:
    """Render the structured comparison window in the selected report language."""

    if not comparison.get("available"):
        return report_text(catalog, "report.comparison_single")
    if comparison.get("window_size") == 1:
        return report_text(catalog, "report.comparison_first_latest")
    return report_text(
        catalog,
        "report.comparison_first_last",
        count=comparison.get("window_size"),
    )


def localized_series_trend(catalog: dict[str, str], trend_direction: Any) -> str:
    """Render a known trend label without exposing an internal i18n key."""

    trend = str(trend_direction or "insufficient").strip().lower()
    if trend not in {"stable", "improving", "declining", "insufficient", "unknown"}:
        trend = "unknown"
    return report_text(catalog, f"report.trend_{trend}")


def localized_series_findings(
    catalog: dict[str, str], series_data: dict[str, Any], warnings: dict[str, Any]
) -> list[str]:
    """Create deterministic, non-diagnostic report findings from measured data."""

    evidence = report_text(
        catalog, f"report.evidence_{series_data.get('evidence_level') or 'insufficient'}"
    )
    findings = [report_text(
        catalog, "report.finding_evidence", sessions=localized_count(catalog, series_data.get("records", 0), "session"), evidence=evidence
    )]
    trend = str(series_data.get("trend_direction") or "insufficient")
    findings.append(report_text(
        catalog,
        "report.finding_stable" if trend == "stable" else "report.finding_change",
    ))
    if warnings:
        findings.append(report_text(
            catalog, "report.finding_quality_warning",
            warnings=localized_warning_names(catalog, warnings),
        ))
    if series_data.get("records", 0) < 10:
        findings.append(report_text(catalog, "report.finding_more_sessions"))
    return findings[:5]


def localized_series_executive_summary(
    catalog: dict[str, str], series_data: dict[str, Any], warnings: dict[str, Any]
) -> str:
    """Summarize evidence and data confidence without medical interpretation."""

    evidence = report_text(
        catalog, f"report.evidence_{series_data.get('evidence_level') or 'insufficient'}"
    )
    trend = localized_series_trend(catalog, series_data.get("trend_direction"))
    limitation = (
        report_text(catalog, "report.executive_summary_warning", warnings=localized_count(catalog, sum(warnings.values()), "warning"))
        if warnings
        else report_text(catalog, "report.executive_summary_no_warning")
    )
    return report_text(
        catalog,
        "report.executive_summary_text",
        sessions=localized_count(catalog, series_data.get("session_count", 0), "session"),
        analyzed=localized_count(catalog, series_data.get("records", 0), "session"),
        evidence=evidence,
        trend=trend,
        quality=format_score(series_data.get("avg_data_quality")),
        limitation=limitation,
    )


def localized_warning_summary(catalog: dict[str, str], warnings: dict[str, Any]) -> str:
    if not warnings:
        return report_text(catalog, "report.warning_none")
    return ", ".join(
        f"{report_text(catalog, f'report.warning_{key}', code=str(key).replace('_', ' '))}: {value}"
        for key, value in warnings.items()
    )


def localized_report_status(catalog: dict[str, str], value: Any) -> str:
    """Render persisted execution state without leaking English enum labels."""

    if value in (None, ""):
        return "-"
    key = str(value).strip().lower()
    aliases = {"collecting": "baseline"}
    return report_text(catalog, f"report.status_{aliases.get(key, key)}")


def localized_warning_list(catalog: dict[str, str], values: Any) -> str:
    if not values:
        return report_text(catalog, "report.warning_none")
    if not isinstance(values, (list, tuple, set)):
        values = [values]
    return "; ".join(
        localized_warning(catalog, value)
        for value in values
    )


def localized_warning_names(catalog: dict[str, str], warnings: dict[str, Any]) -> str:
    """List translated warning names without exposing persistence codes."""

    return ", ".join(
        localized_warning(catalog, code)
        for code in warnings
    )


def localized_warning(catalog: dict[str, str], value: Any) -> str:
    """Render a quality warning without exposing a missing i18n key."""

    key = f"report.warning_{str(value)}"
    translated = report_text(catalog, key)
    return (
        translated
        if translated != key
        else report_text(catalog, "report.warning_unclassified")
    )


def localized_session_interpretation(
    catalog: dict[str, str], analysis: dict[str, Any], analysis_result: dict[str, Any]
) -> str:
    """Use locale-neutral stored facts rather than persisted narration text."""

    return report_text(
        catalog,
        "report.session_interpretation_text",
        score=format_score(analysis.get("overall_score")),
        quality=format_score(analysis.get("data_quality_score")),
        status=localized_report_enum(
            catalog,
            "report.wellness_status",
            analysis_result.get("wellness_status") or "unknown",
        ),
    )


def localized_operator_review(
    catalog: dict[str, str], quality_warnings: Any
) -> str:
    if quality_warnings:
        return report_text(
            catalog,
            "report.operator_review_warnings",
            warnings=localized_warning_list(catalog, quality_warnings),
        )
    return report_text(catalog, "report.operator_review_clear")


def build_session_response_from_analysis(
    analysis: dict[str, Any], analysis_result: dict[str, Any]
) -> dict[str, Any] | None:
    """Rebuild a response fact for historical result rows without persistence."""

    facts = {
        **analysis_result,
        "features": analysis_result.get("features") or analysis.get("features") or {},
        "data_quality_score": analysis_result.get("data_quality_score")
        or analysis.get("data_quality_score"),
    }
    return build_session_fact_sheet(facts).get("session_response")


def response_report_flowables(*, response_presentation, styles, catalog):
    """Render a concise PRE/DURING/POST view from the shared response facts."""

    if not response_presentation:
        return []

    flowables = [
        Paragraph(response_presentation["title"], styles["ReportSection"]),
        Paragraph(report_text(catalog, "report.response_objective_measurements"), styles["NoticeText"]),
        make_response_phase_table(response_presentation, styles=styles, catalog=catalog),
    ]

    delta_rows = response_presentation.get("deltas") or []
    if delta_rows:
        flowables.extend([
            Spacer(1, 4),
            Paragraph(report_text(catalog, "report.response_change"), styles["ReportSubsection"]),
            make_metric_strip([(row["label"], row["delta"]) for row in delta_rows], styles),
        ])

    subjective_rows = response_presentation.get("subjective") or []
    if subjective_rows:
        flowables.extend([
            Spacer(1, 4),
            Paragraph(report_text(catalog, "report.response_self_reported"), styles["BodyText"]),
            make_table([(row["label"], row["value"]) for row in subjective_rows]),
        ])

    flowables.extend([
        Spacer(1, 4),
        make_metric_strip([
            (report_text(catalog, "report.response_completeness"), response_presentation["completeness"]),
            (report_text(catalog, "report.response_data_confidence"), response_presentation["confidence"]),
        ], styles),
    ])
    if response_presentation.get("limitations"):
        flowables.extend([
            Paragraph(report_text(catalog, "report.session_summary_limitations"), styles["ReportSubsection"]),
            *[Paragraph("• " + escape_text(item), styles["NoticeText"])
              for item in response_presentation["limitations"]],
        ])
    return flowables


def customer_insight_flowables(*, insight: dict[str, Any], styles, catalog: dict[str, str]) -> list[Any]:
    """Keep customer actions and confidence ahead of detailed measurements."""

    flowables: list[Any] = []
    if insight.get("changes"):
        flowables.extend([
            Paragraph(report_text(catalog, "customer.what_changed"), styles["ReportSection"]),
            make_metric_strip([
                (row["label"], f"{row['before']} -> {row['after']} ({row['delta']})")
                for row in insight["changes"]
            ], styles),
        ])
    if insight.get("self_reported"):
        flowables.extend([
            Paragraph(report_text(catalog, "customer.how_you_felt"), styles["ReportSection"]),
            make_table([(row["label"], row["value"]) for row in insight["self_reported"]]),
        ])
    if insight.get("watch_items"):
        flowables.extend([
            Paragraph(report_text(catalog, "customer.what_to_watch"), styles["ReportSection"]),
            *[Paragraph("• " + escape_text(item), styles["NoticeText"])
              for item in insight["watch_items"]],
        ])
    flowables.extend([
        Paragraph(report_text(catalog, "customer.next_step"), styles["ReportSection"]),
        Paragraph(escape_text(insight["next_step"]), styles["BodyText"]),
        Spacer(1, 4),
        make_metric_strip([
            (report_text(catalog, "customer.data_confidence"), insight["confidence"]),
        ], styles),
        Paragraph(escape_text(insight["confidence_reason"]), styles["NoticeText"]),
    ])
    return flowables


def make_response_phase_table(response_presentation: dict[str, Any], *, styles, catalog: dict[str, str]) -> Table:
    """Present the captured facts in three phases without inventing values."""

    by_phase = {
        phase: {row["label"]: row["value"] for row in response_presentation.get(phase) or []}
        for phase in ("pre", "during", "post")
    }
    metric_order = []
    for phase in ("pre", "during", "post"):
        for label in by_phase[phase]:
            if label not in metric_order:
                metric_order.append(label)

    body = ParagraphStyle("ResponsePhaseBody", parent=styles["BodyText"], fontSize=8.2, leading=10)
    heading = ParagraphStyle("ResponsePhaseHeading", parent=body, textColor=colors.HexColor("#475569"), fontSize=7.3)
    rows = [[
        Paragraph(report_text(catalog, "report.table_metric"), heading),
        Paragraph(report_text(catalog, "report.response_before"), heading),
        Paragraph(report_text(catalog, "report.response_during"), heading),
        Paragraph(report_text(catalog, "report.response_after"), heading),
    ]]
    not_recorded = report_text(catalog, "report.response_not_recorded")
    for metric in metric_order or [report_text(catalog, "report.response_objective_measurements")]:
        rows.append([
            Paragraph(escape_text(metric), body),
            Paragraph(escape_text(by_phase["pre"].get(metric, not_recorded)), body),
            Paragraph(escape_text(by_phase["during"].get(metric, not_recorded)), body),
            Paragraph(escape_text(by_phase["post"].get(metric, not_recorded)), body),
        ])
    table = Table(rows, colWidths=[120, 120, 120, 120], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e9f5f3")),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#d6dee5")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def localized_session_findings(
    catalog: dict[str, str], analysis: dict[str, Any], response_presentation: dict[str, Any] | None
) -> list[str]:
    """Return a short customer-facing finding list from already calculated facts."""

    findings = [localized_session_interpretation(catalog, analysis, analysis.get("result") or {})]
    if response_presentation:
        findings.extend(response_presentation.get("observations") or [])
        findings.extend(response_presentation.get("limitations") or [])
    return list(dict.fromkeys(findings))[:5]


def localized_phase(catalog: dict[str, str], value: Any) -> str:
    phase = str(value or "").strip().lower()
    return report_text(catalog, f"report.phase_{phase}")


def localized_report_enum(catalog: dict[str, str], prefix: str, value: Any) -> str:
    if value in (None, ""):
        return "-"
    key = f"{prefix}_{str(value).strip().lower()}"
    translated = report_text(catalog, key)
    return translated if translated != key else str(value)


def localized_report_status(catalog: dict[str, str], value: Any) -> str:
    """Render persisted execution state without leaking English enum labels."""

    if value in (None, ""):
        return "-"
    key = str(value).strip().lower()
    aliases = {"collecting": "baseline"}
    return report_text(catalog, f"report.status_{aliases.get(key, key)}")


def localized_warning_list(catalog: dict[str, str], values: Any) -> str:
    if not values:
        return report_text(catalog, "report.warning_none")
    if not isinstance(values, (list, tuple, set)):
        values = [values]
    return "; ".join(
        localized_warning(catalog, value)
        for value in values
    )


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
            name="ReportSubsection",
            parent=styles["Heading2"],
            fontSize=9,
            leading=11,
            textColor=colors.HexColor("#0f766e"),
            spaceBefore=7,
            spaceAfter=4,
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
    research_input = {
        **analysis_result,
        "model_name": analysis_result.get("model_name") or analysis.get("model_name"),
        "model_version": analysis_result.get("model_version") or analysis.get("model_version"),
    }
    research_summary = build_research_summary(research_input, locale=locale) if analysis else None
    session_response = (
        analysis_result.get("session_response")
        if analysis_result
        else None
    )
    if analysis and not session_response:
        session_response = build_session_response_from_analysis(analysis, analysis_result)
    response_presentation = build_localized_session_response(
        session_response, catalog
    ) if session_response else None
    customer_insight = build_session_customer_insight(
        analysis=analysis,
        response_presentation=response_presentation,
        catalog=catalog,
    ) if analysis else None
    client_session_number = session_config.get("client_session_number") or "-"
    program_name = session_config.get("program_name") or report_text(catalog, "report.comparison_single")
    program_progress = (
        report_text(
            catalog,
            "report.program_progress",
            completed=session_config.get("program_completed_sessions"),
            total=session_config.get("program_total_sessions"),
        )
        if session_config.get("program_name")
        else "-"
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
        make_compact_overview(
            session=session,
            subject=subject,
            session_config=session_config,
            program_name=program_name,
            program_progress=program_progress,
            client_session_number=client_session_number,
            styles=styles,
            catalog=catalog,
        ),
    ]

    if customer_insight:
        story.extend(
            [
                KeepTogether(
                    [
                        Paragraph(
                            escape_text(customer_insight["headline"]),
                            styles["ReportSection"],
                        ),
                        Spacer(1, 2),
                        Paragraph(
                            escape_text(customer_insight["status"]),
                            styles["ReportSubsection"],
                        ),
                        Paragraph(
                            escape_text(customer_insight["summary"]),
                            styles["BodyText"],
                        ),
                    ]
                ),
                *customer_insight_flowables(insight=customer_insight, styles=styles, catalog=catalog),
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

    if response_presentation:
        story.extend([
            PageBreak(),
            make_page_header(report_text(catalog, "report.session_response"), styles),
            Spacer(1, 7),
            *response_report_flowables(
                response_presentation=response_presentation,
                styles=styles,
                catalog=catalog,
            ),
        ])

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
                            report_text(catalog, "report.label_data_quality_score"),
                            format_score(analysis.get("data_quality_score")),
                        ),
                        (
                            report_text(catalog, "report.label_coverage"),
                            format_percent(features.get("coverage_percent")),
                        ),
                        (
                            report_text(catalog, "report.label_sync_quality"),
                            format_percent(features.get("match_rate")),
                        ),
                        (report_text(catalog, "report.label_missing_samples"), missing_samples),
                        (
                            report_text(catalog, "report.label_hr_pulse_alignment"),
                            (
                                report_text(catalog, "report.quality_alignment_review")
                                if wellness_flags.get(
                                    "sensor_alignment_warning"
                                )
                                else report_text(catalog, "report.quality_no_alignment_warning")
                            ),
                        ),
                        (
                            report_text(catalog, "report.label_spo2_range"),
                            (
                                report_text(catalog, "report.quality_alignment_review")
                                if wellness_flags.get("oxygenation_drop")
                                else report_text(catalog, "report.quality_no_range_warning")
                            ),
                        ),
                        (
                            report_text(catalog, "report.label_quality_notes"),
                            localized_warning_list(catalog, quality_warnings),
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

    technical_appendix = []
    if research_summary:
        research_facts = research_summary["fact_sheet"]
        research_sections = research_summary["sections"]
        research_narration = research_summary["narration"]
        technical_appendix.extend(
            [
                make_page_header(report_text(catalog, "report.technical_appendix"), styles),
                Spacer(1, 6),
                KeepTogether(
                    [
                        Paragraph(report_text(catalog, "report.research_methods_versions"), styles["ReportSection"]),
                        make_table(
                            [
                                (report_text(catalog, "report.research_fact_sheet"), research_summary.get("fact_sheet_version")),
                                (report_text(catalog, "report.research_narration"), research_narration.get("narration_version")),
                                (report_text(catalog, "report.research_narration_source"), localized_report_enum(catalog, "report.narration_source", research_narration.get("source"))),
                                (report_text(catalog, "report.research_analysis_model"), research_facts["analysis"].get("model_version")),
                                (report_text(catalog, "report.research_hrv_algorithm"), research_facts["measurements"].get("hrv_algorithm_version")),
                                (report_text(catalog, "report.research_hrv_window"), format_measurement(research_facts["measurements"].get("hrv_window_seconds"), " s", 0)),
                            ]
                        ),
                    ]
                ),
                *[
                    KeepTogether(
                        [
                            Paragraph(title, styles["ReportSection"]),
                            Paragraph(escape_text(research_sections[key]), styles["BodyText"]),
                        ]
                    )
                    for key, title in (
                        ("abstract", report_text(catalog, "report.research_abstract")),
                        ("methods", report_text(catalog, "report.research_methods")),
                        ("observations", report_text(catalog, "report.research_observations")),
                        ("interpretation", report_text(catalog, "report.research_interpretation")),
                        ("limitations", report_text(catalog, "report.research_limitations")),
                        ("future_data_required", report_text(catalog, "report.research_future_data")),
                    )
                ],
                Spacer(1, 5),
                Paragraph(escape_text(research_summary["disclaimer"]), styles["NoticeText"]),
            ]
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
                                f"{localized_phase(catalog, segment.get('phase'))}",
                                (
                                    f"{format_measurement(segment.get('actual_duration_min'), ' min', 0)}"
                                    f" {report_text(catalog, 'report.label_at')} {format_measurement(segment.get('actual_ata'), ' ATA', 2)}"
                                    + (
                                        f" - {segment.get('note')}"
                                        if segment.get("note")
                                        else ""
                                    )
                                ),
                            )
                            for segment in session.get("segments") or []
                        ]
                        or [(
                            report_text(catalog, "report.label_timeline"),
                            report_text(catalog, "report.label_no_segment_data"),
                        )]
                    ),
                ]
            ),
            KeepTogether(
                [
                    Paragraph(
                        report_text(catalog, "report.label_check_in_recovery"),
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
                        ],
                        catalog=catalog,
                    ),
                    Spacer(1, 5),
                    Paragraph(
                        "<b>" + escape_text(report_text(catalog, "report.label_check_in_context")) + ":</b> "
                        + escape_text(
                            format_context(
                                phase_metric(
                                    session.get("pre"),
                                    "check_in",
                                ),
                                catalog=catalog,
                            )
                        ),
                        styles["NoticeText"],
                    ),
                    Paragraph(
                        "<b>" + escape_text(report_text(catalog, "report.label_recovery_context")) + ":</b> "
                        + escape_text(
                            format_context(
                                phase_metric(
                                    session.get("post"),
                                    "check_out",
                                ),
                                catalog=catalog,
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
                                report_text(catalog, "report.label_oxygen_flow"),
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
                                report_text(catalog, "report.label_estimated_mask_oxygen"),
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
                                report_text(catalog, "report.label_chamber_temperature"),
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
                                report_text(catalog, "report.label_pressure_deviation"),
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
                                report_text(catalog, "report.label_hr_hrv_samples"),
                                report_data.get("fit_samples"),
                            ),
                            (
                                report_text(catalog, "report.label_spo2_pulse_samples"),
                                report_data.get("csv_samples"),
                            ),
                            (
                                report_text(catalog, "report.label_synchronized_samples"),
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
                                report_text(catalog, "report.label_baseline_status"),
                                localized_report_status(catalog,
                                    wellness_history.get(
                                        "baseline_confidence"
                                    )
                                ),
                            ),
                            (
                                report_text(catalog, "report.label_sessions_last_30_days"),
                                wellness_history.get("unique_sessions_30d"),
                            ),
                            (
                                report_text(catalog, "report.label_rmssd_7_days"),
                                format_measurement(
                                    baseline.get("rmssd_7d"),
                                    " ms",
                                    1,
                                ),
                            ),
                            (
                                report_text(catalog, "report.label_spo2_average"),
                                format_measurement(
                                    baseline.get("spo2_avg"),
                                    "%",
                                    1,
                                ),
                            ),
                            (
                                report_text(catalog, "report.label_spo2_minimum"),
                                format_measurement(
                                    baseline.get("spo2_min"),
                                    "%",
                                    1,
                                ),
                            ),
                            (
                                report_text(catalog, "report.label_baseline_data_quality"),
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

    if technical_appendix:
        story.extend([PageBreak(), *technical_appendix])

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
            name="ReportSubsection",
            parent=styles["Heading2"],
            fontSize=9,
            leading=11,
            textColor=colors.HexColor("#0f766e"),
            spaceAfter=3,
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
    customer_insight = build_series_customer_insight(
        series_data=series_data,
        catalog=catalog,
    )
    warning_summary = localized_warning_summary(catalog, warnings)
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
                        f"{escape_text(report_text(catalog, 'report.label_client'))} {escape_text(series_data.get('user_id'))}"
                        f" &nbsp; | &nbsp; {escape_text(report_text(catalog, 'report.label_range'))}: {escape_text(series_data.get('series_limit'))}"
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
                    customer_insight["sessions_analyzed"],
                ),
                (
                    report_text(catalog, "report.metric_trend"),
                    customer_insight["status"],
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
                Paragraph(customer_insight["headline"], styles["ReportSection"]),
                make_table(
                    [
                        (report_text(catalog, "report.label_client"), series_data.get("user_id")),
                        (report_text(catalog, "report.label_range"), series_data.get("series_limit")),
                        (report_text(catalog, "report.label_protocol"), protocol.get("name") or protocol.get("code")),
                        (report_text(catalog, "report.label_total_sessions"), series_data.get("session_count")),
                        (report_text(catalog, "report.label_analyzed_sessions"), series_data.get("records")),
                        (report_text(catalog, "customer.data_confidence"), customer_insight["confidence"]),
                        (report_text(catalog, "report.label_review_flags"), flagged_sessions),
                        (
                            report_text(catalog, "report.label_latest_session"),
                            latest_session.get("session_id") or "-",
                        ),
                        (
                            report_text(catalog, "report.label_latest_score"),
                            format_score(series_data.get("latest_score")),
                        ),
                    ]
                ),
            ]
        ),
        KeepTogether(
            [
                Paragraph(customer_insight["status"], styles["ReportSubsection"]),
                Paragraph(
                    escape_text(customer_insight["summary"]),
                    styles["BodyText"],
                ),
                Paragraph(escape_text(customer_insight["pattern"]), styles["BodyText"]),
            ]
        ),
        *make_series_trend_flowables(analyses, styles=styles, catalog=catalog),
        *(
            [
                KeepTogether(
                    [
                        Paragraph(report_text(catalog, "customer.what_to_watch"), styles["ReportSection"]),
                        *[
                            Paragraph("• " + escape_text(finding), styles["BodyText"])
                            for finding in customer_insight["watch_items"]
                        ],
                    ]
                )
            ]
            if customer_insight["watch_items"]
            else []
        ),
        KeepTogether(
            [
                Paragraph(report_text(catalog, "customer.next_step"), styles["ReportSection"]),
                Paragraph(escape_text(customer_insight["next_step"]), styles["BodyText"]),
            ]
        ),
        KeepTogether(
            [
                Paragraph(
                    escape_text(localized_series_comparison(catalog, comparison)),
                    styles["ReportSection"],
                ),
                *(
                    [
                        make_table(
                            [
                                (
                                    report_text(catalog, "report.label_wellness_score"),
                                    (
                                        f"{format_score(comparison.get('first_avg_score'))}"
                                        f" -> {format_score(comparison.get('last_avg_score'))}"
                                        f" ({format_delta_text(comparison.get('score_delta'))})"
                                    ),
                                ),
                                (
                                    report_text(catalog, "report.label_data_quality"),
                                    (
                                        f"{format_score(comparison.get('first_avg_data_quality'))}"
                                        f" -> {format_score(comparison.get('last_avg_data_quality'))}"
                                        f" ({format_delta_text(comparison.get('data_quality_delta'))})"
                                    ),
                                ),
                                *series_comparison_measurement_rows(comparison, catalog),
                            ]
                        ),
                        *(
                            [Paragraph(report_text(catalog, "customer.comparison_measurement_unavailable"), styles["NoticeText"])]
                            if any(
                                comparison.get(field) in (None, "")
                                for field in (
                                    "first_avg_heart_rate", "last_avg_heart_rate",
                                    "first_avg_hrv", "last_avg_hrv",
                                    "first_avg_spo2", "last_avg_spo2",
                                )
                            )
                            else []
                        ),
                    ]
                    if comparison.get("available")
                    else [
                        Paragraph(
                            escape_text(
                                report_text(catalog, "report.comparison_single")
                            ),
                            styles["NoticeText"],
                        )
                    ]
                ),
            ]
        ),
        KeepTogether(
            [
                Paragraph(
                    report_text(catalog, "report.data_quality_confidence"),
                    styles["ReportSection"],
                ),
                make_table(
                    [
                        (report_text(catalog, "report.label_average_coverage"), format_percent(series_data.get("avg_coverage"))),
                        (report_text(catalog, "report.label_average_sync"), format_percent(series_data.get("avg_match_rate"))),
                        (report_text(catalog, "report.label_missing_samples"), quality_engine.get("total_missing_samples")),
                        (report_text(catalog, "report.label_sensor_gap_sessions"), quality_engine.get("sensor_gap_sessions")),
                        (
                            report_text(catalog, "report.label_hr_pulse_mismatch"),
                            quality_engine.get("hr_pulse_mismatch_sessions"),
                        ),
                        (
                            report_text(catalog, "report.label_spo2_warnings"),
                            quality_engine.get("spo2_warning_sessions"),
                        ),
                        (report_text(catalog, "report.label_warning_summary"), warning_summary),
                    ]
                ),
                Spacer(1, 5),
                Paragraph(
                    escape_text(
                        report_text(catalog, "report.quality_confidence"),
                    ),
                    styles["NoticeText"],
                ),
            ]
        ),
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
                    report_text(catalog, "report.label_session_number", number=escape_text(session_number))
                    + " &nbsp; | &nbsp; "
                    f"{escape_text(format_report_datetime(session.get('created_at'), catalog=catalog))}",
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


def make_series_trend_flowables(analyses: list[dict[str, Any]], *, styles, catalog: dict[str, str]) -> list[Any]:
    """Render a restrained score trend only when comparable session facts exist."""

    points = []
    for row in analyses:
        score = row.get("overall_score")
        try:
            points.append(float(score))
        except (TypeError, ValueError):
            continue
    if len(points) < 2:
        return [
            Paragraph(report_text(catalog, "report.longitudinal_view"), styles["ReportSection"]),
            Paragraph(report_text(catalog, "report.longitudinal_insufficient"), styles["NoticeText"]),
        ]

    width, height, margin = 480, 132, 22
    drawing = Drawing(width, height)
    drawing.add(String(0, height - 4, report_text(catalog, "report.trend_score_chart"), fontName=register_report_font(), fontSize=8.5, fillColor=colors.HexColor("#475569")))
    chart_height = height - 32
    drawing.add(Line(margin, 18, width - 4, 18, strokeColor=colors.HexColor("#cbd5e1"), strokeWidth=0.6))
    drawing.add(Line(margin, 18, margin, chart_height, strokeColor=colors.HexColor("#cbd5e1"), strokeWidth=0.6))
    # Scores are bounded, but the chart scale follows the observed range so a
    # genuine small change remains legible in print.
    minimum = max(0.0, min(points) - 5)
    maximum = min(100.0, max(points) + 5)
    span = max(1.0, maximum - minimum)
    previous = None
    for index, value in enumerate(points):
        x = margin + ((width - margin - 10) * index / max(1, len(points) - 1))
        y = 18 + ((chart_height - 18) * (value - minimum) / span)
        if previous:
            drawing.add(Line(previous[0], previous[1], x, y, strokeColor=colors.HexColor("#0f9488"), strokeWidth=2))
        drawing.add(Line(x, y - 2, x, y + 2, strokeColor=colors.HexColor("#0f9488"), strokeWidth=3))
        drawing.add(String(x - 8, 5, str(index + 1), fontName=register_report_font(), fontSize=7, fillColor=colors.HexColor("#64748b")))
        previous = (x, y)
    drawing.add(String(0, chart_height - 2, f"{maximum:g}", fontName=register_report_font(), fontSize=6.5, fillColor=colors.HexColor("#64748b")))
    drawing.add(String(0, 17, f"{minimum:g}", fontName=register_report_font(), fontSize=6.5, fillColor=colors.HexColor("#64748b")))
    return [
        Paragraph(report_text(catalog, "report.longitudinal_view"), styles["ReportSection"]),
        drawing,
        Paragraph(report_text(catalog, "report.trend_chart_caption", count=len(points)), styles["NoticeText"]),
    ]


def make_compact_overview(
    *,
    session: dict[str, Any],
    subject: dict[str, Any],
    session_config: dict[str, Any],
    program_name: str,
    program_progress: str,
    client_session_number: Any,
    styles,
    catalog: dict[str, str],
) -> Table:
    """Keep executive metadata compact so the client insight leads page one."""

    label_style = ParagraphStyle(
        "OverviewLabel", parent=styles["MetricLabel"], alignment=0, fontSize=7.3
    )
    value_style = ParagraphStyle(
        "OverviewValue", parent=styles["BodyText"], fontSize=8.7, leading=10.5
    )
    rows = [
        (report_text(catalog, "report.label_client"), subject.get("user_id")),
        (report_text(catalog, "report.client_session"), report_text(catalog, "report.label_session_number", number=client_session_number)),
        (report_text(catalog, "report.label_date"), format_report_datetime(session.get("created_at"), catalog=catalog)),
        (report_text(catalog, "report.label_protocol"), session.get("protocol_name")),
        (report_text(catalog, "report.label_program"), f"{program_name} - {program_progress}"),
        (report_text(catalog, "report.label_duration"), format_measurement(session.get("total_duration_min"), " min", 0)),
    ]
    cells = []
    for index in range(0, len(rows), 2):
        left_label, left_value = rows[index]
        right_label, right_value = rows[index + 1]
        cells.append([
            Paragraph(escape_text(left_label), label_style),
            Paragraph(escape_text(left_value), value_style),
            Paragraph(escape_text(right_label), label_style),
            Paragraph(escape_text(right_value), value_style),
        ])
    table = Table(cells, colWidths=[116, 124, 116, 124])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fbfdfd")),
        ("LINEBELOW", (0, 0), (-1, -1), 0.2, colors.HexColor("#dce8e6")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


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
    table = Table([cells], colWidths=[480 / max(1, len(cells))] * len(cells))
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


def make_comparison_table(
    rows: list[tuple[str, Any, Any]], *, catalog: dict[str, str]
) -> Table:
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
            Paragraph(report_text(catalog, "report.table_metric"), header_style),
            Paragraph(report_text(catalog, "report.table_check_in"), header_style),
            Paragraph(report_text(catalog, "report.table_recovery"), header_style),
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
            Paragraph(report_text(catalog, "report.label_average_hr"), header_style),
            Paragraph(report_text(catalog, "report.label_average_hrv"), header_style),
            Paragraph("SPO2", header_style),
            Paragraph(report_text(catalog, "report.table_review"), header_style),
        ]
    ]

    for index, row in enumerate(analyses, start=1):
        rows.append(
            [
                Paragraph(
                    escape_text(
                        f"{report_text(catalog, 'report.table_session')} {index}\n"
                        f"ID: {row.get('session_id') or '-'}"
                    ),
                    body_style,
                ),
                Paragraph(escape_text(format_report_datetime(row.get("created_at"), catalog=catalog)), body_style),
                Paragraph(escape_text(format_score(row.get("overall_score"))), body_style),
                Paragraph(escape_text(format_score(row.get("data_quality_score"))), body_style),
                Paragraph(escape_text(format_measurement(row.get("avg_reference_heart_rate"), " bpm", 0)), body_style),
                Paragraph(escape_text(format_measurement(row.get("avg_hrv"), " ms", 1)), body_style),
                Paragraph(escape_text(format_measurement(row.get("avg_spo2"), "%", 1)), body_style),
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
        colWidths=[94, 72, 54, 54, 50, 50, 44, 62],
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


def series_comparison_measurement_rows(
    comparison: dict[str, Any], catalog: dict[str, str]
) -> list[tuple[str, str]]:
    """Return only genuinely comparable physiological measurements.

    A dash-to-dash row implies a comparison where neither end exists.  The
    series report instead omits that row and adds one localized availability
    note in the calling section.
    """

    definitions = (
        ("report.label_average_hr", "first_avg_heart_rate", "last_avg_heart_rate", "heart_rate_delta", " bpm", 0),
        ("report.label_average_hrv", "first_avg_hrv", "last_avg_hrv", "hrv_delta", " ms", 1),
        ("report.label_average_spo2", "first_avg_spo2", "last_avg_spo2", "spo2_delta", "%", 1),
    )
    rows: list[tuple[str, str]] = []
    for label_key, first_key, last_key, delta_key, suffix, decimals in definitions:
        first, last = comparison.get(first_key), comparison.get(last_key)
        if first in (None, "") or last in (None, ""):
            continue
        rows.append(
            (
                report_text(catalog, label_key),
                (
                    f"{format_measurement(first, suffix, decimals)}"
                    f" -> {format_measurement(last, suffix, decimals)}"
                    f" ({format_delta_text(comparison.get(delta_key))})"
                ),
            )
        )
    return rows


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
        report_text(catalog, "report.page", page=doc.page),
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


def format_report_datetime(
    value: Any, *, catalog: dict[str, str] | None = None
) -> str:
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

    if catalog and catalog.get("report.page", "").startswith("Strona"):
        months = (
            "sty", "lut", "mar", "kwi", "maj", "cze", "lip", "sie",
            "wrz", "paź", "lis", "gru",
        )
        return f"{parsed.day:02d} {months[parsed.month - 1]} {parsed.year}, {parsed:%H:%M}"
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


def format_context(value: Any, *, catalog: dict[str, str]) -> str:
    """Format optional check-in/check-out context for the PDF."""

    if not isinstance(value, dict):
        return "-"

    pairs = []
    for key, item in value.items():
        if item in (None, ""):
            continue

        label = report_text(catalog, f"report.context_{key}")
        if label == f"report.context_{key}":
            label = key.replace("_", " ").title()
        if isinstance(item, bool):
            item = report_text(catalog, "report.context_value_yes" if item else "report.context_value_no")
        elif isinstance(item, str):
            item = localized_report_enum(catalog, "report.context_value", item)
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
