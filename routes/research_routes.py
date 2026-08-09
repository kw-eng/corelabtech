# routes/research_routes.py
"""Research-facing Flask routes.

This blueprint serves the chamber workflow, upload APIs, merge/analysis APIs,
admin compatibility endpoints and public research pages.
"""

import hashlib
import os
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

from psycopg2 import IntegrityError
from flask import (
    abort,
    Blueprint,
    current_app,
    jsonify,
    render_template,
    request,
    send_file,
)
from flask_login import current_user, login_required
from werkzeug.security import generate_password_hash

from auth.decorators import role_required
from auth.access_policy import can_access_client_record
from core.telemetry.device_catalog import (
    DEVICE_COMPATIBILITY_VERSION,
    device_catalog,
    device_compatibility_matrix,
)
from database_postgres import db

from repositories.analysis_repository import (
    get_latest_ai_result,
    list_analyses,
)

from repositories.data_repository import (
    list_session_data_sources,
    load_csv,
    load_fit,
)

from repositories.merge_repository import (
    get_latest_completed_merge_job,
    load_merged_measurements,
)
from repositories.wellness_repository import (
    get_wellness_summary,
)
from repositories.recovery_repository import (
    create_recovery_follow_up,
    normalize_recovery_follow_up_payload,
)

from security.csrf import csrf
from security.limiter import limiter
from security.upload_validation import (
    safe_upload_filename,
    validate_extension,
    validate_file_size,
)

from services.analysis_service import (
    AnalysisInputMissingError,
    get_analysis_model_manifest,
    run_session_analysis,
)
from services.audit_service import record_audit_event
from services.llm_observability import list_llm_observability
from services.client_data_service import build_client_export

from services.data_ingestion import (
    DataIngestionError,
    DuplicateImportError,
    import_csv_file,
    import_external_telemetry_file,
    import_fit_file,
    preview_telemetry_file,
)

from services.data_merge import (
    MergeInputMissingError,
    merge_session_data,
)

from services.session_service import (
    complete_session,
    delete_research_sessions,
    get_research_session,
    list_research_sessions,
    save_session_phase,
)
from services.report_generator import (
    generate_report_for_session,
    generate_series_report_for_client,
)
from services.series_service import get_user_series_trends
from services.trend_narration import build_trend_ai_view
from services.research_summary import build_research_summary
from services.traceability_service import get_session_traceability


#------------------------------
#HELPERS
#------------------------------

research_bp = Blueprint(
    "research",
    __name__,
)

TEMP_UPLOAD_DIRECTORY = Path(
    "data/uploads/temp"
)

UPLOAD_LIMIT = "60 per minute"
PERF_LIMIT = "300 per minute"
DEFAULT_PREVIEW_LIMIT = 500
MAX_PREVIEW_LIMIT = 5000


def clean_value(value) -> str:
    return (
        str(value).strip()
        if value is not None
        else ""
    )


def parse_preview_limit(
    value,
    *,
    default: int = DEFAULT_PREVIEW_LIMIT,
    maximum: int = MAX_PREVIEW_LIMIT,
) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default

    if parsed <= 0:
        return default

    return min(parsed, maximum)


def parse_optional_int(value) -> int | None:
    if value in (None, ""):
        return None

    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None

    return parsed if parsed > 0 else None


def current_user_id() -> str | None:
    return (
        getattr(current_user, "user_id", None)
        or getattr(current_user, "email", None)
    )


def audit_request_metadata() -> dict[str, str | None]:
    """Return bounded request metadata for an audit event."""

    return {
        "ip_address": request.headers.get("X-Forwarded-For", request.remote_addr),
        "user_agent": clean_value(request.user_agent.string)[:500] or None,
    }


def write_audit_event(
    *,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    client_id: str | None = None,
    session_id: str | None = None,
    details: dict | None = None,
) -> None:
    """Commit an audit event after a successful route-level operation."""

    connection = db()
    cursor = connection.cursor()

    try:
        record_audit_event(
            cursor,
            actor_user_id=current_user_id(),
            actor_role=getattr(current_user, "role", None),
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            client_id=client_id,
            session_id=session_id,
            details=details,
            **audit_request_metadata(),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


def ensure_extended_wellness_programs(cursor) -> None:
    """Ensure default long-range wellness programs exist for this tenant."""

    cursor.execute(
        """
        WITH default_protocol AS (
            SELECT
                p.protocol_id,
                p.organization_id
            FROM protocols p
            WHERE p.organization_id = %s
              AND p.code = 'WELLNESS_1_5'
              AND p.is_active = TRUE
            ORDER BY p.protocol_id
            LIMIT 1
        ),
        program_rows AS (
            SELECT
                'RECOVERY_50' AS code,
                'Recovery 50' AS name,
                50 AS total_sessions,
                3 AS frequency_per_week,
                'Fifty-session wellness response tracking program.' AS description
            UNION ALL
            SELECT
                'RECOVERY_100',
                'Recovery 100',
                100,
                3,
                'One-hundred-session longitudinal wellness tracking program.'
        )
        INSERT INTO wellness_programs (
            organization_id,
            location_id,
            protocol_id,
            code,
            name,
            total_sessions,
            frequency_per_week,
            description
        )
        SELECT
            dp.organization_id,
            %s,
            dp.protocol_id,
            pr.code,
            pr.name,
            pr.total_sessions,
            pr.frequency_per_week,
            pr.description
        FROM default_protocol dp
        CROSS JOIN program_rows pr
        ON CONFLICT (organization_id, code)
        DO UPDATE SET
            name = EXCLUDED.name,
            total_sessions = EXCLUDED.total_sessions,
            frequency_per_week = EXCLUDED.frequency_per_week,
            description = EXCLUDED.description,
            is_active = TRUE,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            current_user.organization_id,
            current_user.location_id,
        ),
    )


def record_session_consent_and_audit(
    *,
    session_id: str,
    client_id: str,
    consent: dict,
) -> None:
    """Persist the versioned wellness acknowledgement and session audit."""

    connection = db()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO consent_records (
                client_id,
                session_id,
                consent_type,
                accepted,
                terms_version,
                recorded_by,
                recorded_at,
                metadata_json
            )
            VALUES (
                %s, %s, 'wellness_session',
                TRUE, %s, %s, %s, %s::jsonb
            )
            """,
            (
                client_id,
                session_id,
                consent.get("terms_version"),
                consent.get("recorded_by"),
                consent.get("recorded_at"),
                '{"scope":"wellness_and_educational_insights"}',
            ),
        )
        record_audit_event(
            cursor,
            actor_user_id=current_user_id(),
            actor_role=current_user.role,
            action="session.complete",
            entity_type="session",
            entity_id=session_id,
            client_id=client_id,
            session_id=session_id,
            details={
                "consent_version": consent.get("terms_version"),
            },
            **audit_request_metadata(),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


def create_temp_path(filename: str) -> Path:
    TEMP_UPLOAD_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    return TEMP_UPLOAD_DIRECTORY / (
        f"{uuid.uuid4()}_{filename}"
    )


def remove_temp_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        traceback.print_exc()


def error_response(
    message: str,
    status_code: int,
):
    return jsonify({
        "status": "error",
        "error": message,
    }), status_code


# =========================================================
# PAGES
# =========================================================

@research_bp.route("/platform")
def research_platform():
    return render_template(
        "research_platform.html"
    )


@research_bp.route("/research")
@login_required
@role_required(
    "viewer",
    "operator",
    "researcher",
    "admin",
)
def research_dashboard():
    return render_template(
        "research_dashboard.html"
    )


@research_bp.route("/operator-dashboard")
@login_required
@role_required(
    "operator",
    "researcher",
    "admin",
)
def operator_dashboard():
    return render_template(
        "operator_dashboard.html"
    )


@research_bp.route("/chamber")
@login_required
@role_required(
    "operator",
    "researcher",
    "admin",
)
def chamber_testing():
    return render_template(
        "chamber_testing.html"
    )


@research_bp.route("/ai-lab")
@login_required
@role_required(
    "viewer",
    "operator",
    "researcher",
    "admin",
)
def ai_lab():
    return render_template(
        "ai_lab.html"
    )


@research_bp.route("/ai-testing-lab")
def ai_testing_lab_public():
    if not current_app.config["INTERNAL_TOOLS_ENABLED"]:
        abort(404)
    return render_template(
        "ai_testing_lab_public.html"
    )


@research_bp.route("/performance-tests")
@login_required
@role_required("admin")
def performance_tests():
    if not current_app.config["INTERNAL_TOOLS_ENABLED"]:
        abort(404)
    return render_template(
        "performance_tests.html"
    )


@research_bp.route("/admin")
@login_required
@role_required("admin")
def admin_panel():
    return render_template(
        "admin_panel.html",
        analysis_model=get_analysis_model_manifest(),
    )


@research_bp.route("/admin/accounts")
@login_required
@role_required("admin")
def admin_accounts():
    return render_template(
        "admin_accounts.html"
    )


# =========================================================
# CHAMBERS / PROTOCOLS
# =========================================================

@research_bp.route("/api/device-catalog", methods=["GET"])
@login_required
@role_required("admin")
@limiter.limit(PERF_LIMIT)
def telemetry_device_catalog():
    """Return technical device metadata for administrative diagnostics."""

    return jsonify({
        "version": "device-catalog-v2",
        "compatibility_version": DEVICE_COMPATIBILITY_VERSION,
        "devices": device_catalog(),
        "compatibility": device_compatibility_matrix(),
    })

@research_bp.route("/api/chambers", methods=["GET"])
@login_required
@role_required("admin", "researcher", "operator")
@limiter.limit(PERF_LIMIT)
def chambers():
    connection = db()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT
                chamber_id,
                code,
                name,
                location,
                manufacturer,
                model,
                serial_number,
                max_ata,
                pressure_input_unit
            FROM chambers
            WHERE is_active = TRUE
              AND organization_id = %s
            ORDER BY name
            """,
            (current_user.organization_id,),
        )
        return jsonify(
            [
                {
                    "chamber_id": row[0],
                    "code": row[1],
                    "name": row[2],
                    "location": row[3],
                    "manufacturer": row[4],
                    "model": row[5],
                    "serial_number": row[6],
                    "max_ata": row[7],
                    "pressure_input_unit": row[8],
                }
                for row in cursor.fetchall()
            ]
        )
    finally:
        cursor.close()
        connection.close()


@csrf.exempt
@research_bp.route("/api/chambers", methods=["POST"])
@login_required
@role_required("admin", "researcher")
@limiter.limit("30 per minute")
def create_chamber():
    data = request.get_json(silent=True) or {}
    code = clean_value(data.get("code")).upper()
    name = clean_value(data.get("name"))
    unit = clean_value(data.get("pressure_input_unit")) or "kpa_gauge"

    if not code or not name:
        return error_response("code and name are required", 400)
    if unit not in {"ata", "kpa_gauge", "kpa_absolute"}:
        return error_response("invalid pressure_input_unit", 400)

    connection = db()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO chambers (
                code,
                name,
                location,
                manufacturer,
                model,
                serial_number,
                max_ata,
                pressure_input_unit,
                organization_id,
                location_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING chamber_id
            """,
            (
                code,
                name,
                clean_value(data.get("location")) or None,
                clean_value(data.get("manufacturer")) or None,
                clean_value(data.get("model")) or None,
                clean_value(data.get("serial_number")) or None,
                data.get("max_ata") or 1.5,
                unit,
                current_user.organization_id,
                current_user.location_id,
            ),
        )
        chamber_id = cursor.fetchone()[0]
        record_audit_event(
            cursor,
            actor_user_id=current_user_id(),
            actor_role=current_user.role,
            action="chamber.create",
            entity_type="chamber",
            entity_id=str(chamber_id),
            details={"code": code, "name": name},
            **audit_request_metadata(),
        )
        connection.commit()
        return jsonify({"status": "created", "chamber_id": chamber_id}), 201
    except IntegrityError:
        connection.rollback()
        return error_response("chamber code already exists", 409)
    except Exception as exc:
        connection.rollback()
        return error_response(str(exc), 400)
    finally:
        cursor.close()
        connection.close()


@research_bp.route("/api/protocols", methods=["GET"])
@login_required
@role_required("admin", "researcher", "operator")
@limiter.limit(PERF_LIMIT)
def protocols():
    connection = db()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT
                protocol_id,
                code,
                name,
                mode,
                target_ata,
                planned_duration_min,
                compression_time_min,
                exposure_time_min,
                decompression_time_min,
                oxygen_mode,
                oxygen_flow_lpm,
                oxygen_percent
            FROM protocols
            WHERE is_active = TRUE
              AND mode = 'wellness'
              AND organization_id = %s
            ORDER BY target_ata, name
            """,
            (current_user.organization_id,),
        )
        return jsonify(
            [
                {
                    "protocol_id": row[0],
                    "code": row[1],
                    "name": row[2],
                    "mode": row[3],
                    "target_ata": row[4],
                    "planned_duration_min": row[5],
                    "compression_time_min": row[6],
                    "exposure_time_min": row[7],
                    "decompression_time_min": row[8],
                    "oxygen_mode": row[9],
                    "oxygen_flow_lpm": row[10],
                    "oxygen_percent": row[11],
                }
                for row in cursor.fetchall()
            ]
        )
    finally:
        cursor.close()
        connection.close()


@research_bp.route("/api/organization/context", methods=["GET"])
@login_required
@role_required("admin", "researcher", "operator")
def organization_context():
    """Return the commercial tenant and location visible to this account."""

    connection = db()
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            SELECT
                o.organization_id,
                o.code,
                o.name,
                l.location_id,
                l.code,
                l.name,
                l.timezone
            FROM organizations o
            LEFT JOIN organization_locations l
                ON l.location_id = %s
            WHERE o.organization_id = %s
            LIMIT 1
            """,
            (
                current_user.location_id,
                current_user.organization_id,
            ),
        )
        row = cursor.fetchone()
        if not row:
            return error_response("organization context unavailable", 404)
        return jsonify(
            {
                "organization_id": row[0],
                "organization_code": row[1],
                "organization_name": row[2],
                "location_id": row[3],
                "location_code": row[4],
                "location_name": row[5],
                "timezone": row[6],
            }
        )
    finally:
        cursor.close()
        connection.close()


@research_bp.route("/api/programs", methods=["GET"])
@login_required
@role_required("admin", "researcher", "operator")
def wellness_programs():
    """List active wellness packages for the current organization."""

    connection = db()
    cursor = connection.cursor()
    try:
        ensure_extended_wellness_programs(cursor)
        connection.commit()

        cursor.execute(
            """
            SELECT
                wp.program_id,
                wp.code,
                wp.name,
                wp.total_sessions,
                wp.frequency_per_week,
                wp.description,
                wp.protocol_id,
                p.name,
                p.target_ata,
                p.planned_duration_min
            FROM wellness_programs wp
            JOIN protocols p ON p.protocol_id = wp.protocol_id
            WHERE wp.organization_id = %s
              AND wp.is_active = TRUE
            ORDER BY wp.total_sessions, wp.name
            """,
            (current_user.organization_id,),
        )
        return jsonify(
            [
                {
                    "program_id": row[0],
                    "code": row[1],
                    "name": row[2],
                    "total_sessions": row[3],
                    "frequency_per_week": row[4],
                    "description": row[5],
                    "protocol_id": row[6],
                    "protocol_name": row[7],
                    "target_ata": row[8],
                    "planned_duration_min": row[9],
                }
                for row in cursor.fetchall()
            ]
        )
    finally:
        cursor.close()
        connection.close()


@csrf.exempt
@research_bp.route("/api/client-programs", methods=["GET", "POST"])
@login_required
@role_required("admin", "researcher", "operator")
def client_programs():
    """List or create package enrollments within the current organization."""

    connection = db()
    cursor = connection.cursor()
    try:
        if request.method == "POST":
            data = request.get_json(silent=True) or {}
            client_id = clean_value(data.get("client_id"))
            program_id = parse_optional_int(data.get("program_id"))
            if not client_id or program_id is None:
                return error_response("client_id and program_id are required", 400)

            cursor.execute(
                """
                SELECT 1
                FROM users u
                JOIN wellness_programs wp
                    ON wp.organization_id = u.organization_id
                WHERE u.user_id = %s
                  AND u.organization_id = %s
                  AND wp.program_id = %s
                  AND wp.is_active = TRUE
                LIMIT 1
                """,
                (
                    client_id,
                    current_user.organization_id,
                    program_id,
                ),
            )
            if not cursor.fetchone():
                return error_response("client or program unavailable", 404)

            cursor.execute(
                """
                SELECT enrollment_id
                FROM client_programs
                WHERE client_id = %s
                  AND program_id = %s
                  AND status = 'active'
                LIMIT 1
                """,
                (client_id, program_id),
            )
            existing = cursor.fetchone()
            if existing:
                enrollment_id = existing[0]
            else:
                cursor.execute(
                    """
                    INSERT INTO client_programs (
                        program_id,
                        client_id,
                        created_by
                    )
                    VALUES (%s, %s, %s)
                    RETURNING enrollment_id
                    """,
                    (
                        program_id,
                        client_id,
                        current_user_id(),
                    ),
                )
                enrollment_id = cursor.fetchone()[0]

            record_audit_event(
                cursor,
                actor_user_id=current_user_id(),
                actor_role=current_user.role,
                action="program.enroll",
                entity_type="client_program",
                entity_id=str(enrollment_id),
                client_id=client_id,
                details={"program_id": program_id},
                **audit_request_metadata(),
            )
            connection.commit()
            return jsonify(
                {
                    "status": "active",
                    "enrollment_id": enrollment_id,
                    "client_id": client_id,
                    "program_id": program_id,
                }
            ), 201

        client_id = clean_value(request.args.get("client_id"))
        if not client_id:
            return error_response("client_id is required", 400)
        cursor.execute(
            """
            SELECT
                cp.enrollment_id,
                cp.status,
                cp.started_at,
                cp.completed_at,
                wp.program_id,
                wp.code,
                wp.name,
                wp.total_sessions,
                wp.frequency_per_week,
                wp.protocol_id,
                COUNT(fs.id) FILTER (WHERE fs.completed = 1) AS completed_sessions
            FROM client_programs cp
            JOIN wellness_programs wp
                ON wp.program_id = cp.program_id
            JOIN users u ON u.user_id = cp.client_id
            LEFT JOIN full_sessions fs
                ON fs.program_enrollment_id = cp.enrollment_id
            WHERE cp.client_id = %s
              AND u.organization_id = %s
              AND cp.status IN ('active', 'paused')
            GROUP BY
                cp.enrollment_id,
                cp.status,
                cp.started_at,
                cp.completed_at,
                wp.program_id,
                wp.code,
                wp.name,
                wp.total_sessions,
                wp.frequency_per_week,
                wp.protocol_id
            ORDER BY wp.total_sessions, wp.name, cp.created_at DESC
            """,
            (
                client_id,
                current_user.organization_id,
            ),
        )
        return jsonify(
            [
                {
                    "enrollment_id": row[0],
                    "status": row[1],
                    "started_at": row[2].isoformat() if row[2] else None,
                    "completed_at": row[3].isoformat() if row[3] else None,
                    "program_id": row[4],
                    "program_code": row[5],
                    "program_name": row[6],
                    "total_sessions": row[7],
                    "frequency_per_week": row[8],
                    "protocol_id": row[9],
                    "completed_sessions": row[10],
                    "remaining_sessions": max(0, row[7] - row[10]),
                }
                for row in cursor.fetchall()
            ]
        )
    except Exception as exc:
        connection.rollback()
        return error_response(str(exc), 400)
    finally:
        cursor.close()
        connection.close()


@csrf.exempt
@research_bp.route("/api/client-programs/<int:enrollment_id>", methods=["PATCH"])
@login_required
@role_required("admin", "researcher", "operator")
@limiter.limit("30 per minute")
def update_client_program_status(enrollment_id: int):
    """Pause, resume or cancel one client program enrollment."""

    data = request.get_json(silent=True) or {}
    status = clean_value(data.get("status")).lower()

    if status not in {"active", "paused", "cancelled"}:
        return error_response("invalid program status", 400)

    connection = db()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT
                cp.client_id,
                cp.status,
                wp.program_id,
                wp.name
            FROM client_programs cp
            JOIN wellness_programs wp
                ON wp.program_id = cp.program_id
            JOIN users u
                ON u.user_id = cp.client_id
            WHERE cp.enrollment_id = %s
              AND u.organization_id = %s
            LIMIT 1
            """,
            (
                enrollment_id,
                current_user.organization_id,
            ),
        )
        row = cursor.fetchone()

        if not row:
            return error_response("program enrollment not found", 404)

        client_id = row[0]
        previous_status = row[1]

        cursor.execute(
            """
            UPDATE client_programs
            SET
                status = %s,
                completed_at = CASE
                    WHEN %s = 'cancelled' THEN CURRENT_DATE
                    ELSE NULL
                END,
                updated_at = CURRENT_TIMESTAMP
            WHERE enrollment_id = %s
            """,
            (
                status,
                status,
                enrollment_id,
            ),
        )
        record_audit_event(
            cursor,
            actor_user_id=current_user_id(),
            actor_role=current_user.role,
            action="program.status_update",
            entity_type="client_program",
            entity_id=str(enrollment_id),
            client_id=client_id,
            details={
                "previous_status": previous_status,
                "new_status": status,
                "program_id": row[2],
                "program_name": row[3],
            },
            **audit_request_metadata(),
        )
        connection.commit()

        return jsonify({
            "status": status,
            "enrollment_id": enrollment_id,
            "client_id": client_id,
        })

    except Exception as exc:
        connection.rollback()
        traceback.print_exc()
        return error_response(str(exc), 500)

    finally:
        cursor.close()
        connection.close()


@research_bp.route("/api/admin/audit-log", methods=["GET"])
@login_required
@role_required("admin")
@limiter.limit("60 per minute")
def audit_log():
    """Return a bounded, metadata-only operational audit feed."""

    limit = parse_preview_limit(
        request.args.get("limit"),
        default=100,
        maximum=500,
    )
    client_id = clean_value(request.args.get("client_id"))
    connection = db()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT
                audit_id,
                actor_user_id,
                actor_role,
                action,
                entity_type,
                entity_id,
                client_id,
                session_id,
                outcome,
                details_json,
                created_at
            FROM audit_log
            WHERE (%s = '' OR client_id = %s)
            ORDER BY created_at DESC, audit_id DESC
            LIMIT %s
            """,
            (
                client_id,
                client_id,
                limit,
            ),
        )
        return jsonify(
            {
                "status": "ok",
                "events": [
                    {
                        "audit_id": row[0],
                        "actor_user_id": row[1],
                        "actor_role": row[2],
                        "action": row[3],
                        "entity_type": row[4],
                        "entity_id": row[5],
                        "client_id": row[6],
                        "session_id": row[7],
                        "outcome": row[8],
                        "details": row[9] or {},
                        "created_at": (
                            row[10].isoformat()
                            if row[10]
                            else None
                        ),
                    }
                    for row in cursor.fetchall()
                ],
            }
        )
    finally:
        cursor.close()
        connection.close()


@research_bp.route("/api/admin/llm-observability", methods=["GET"])
@login_required
@role_required("admin")
@limiter.limit("30 per minute")
def llm_observability():
    """Return aggregated optional-LLM reliability and usage metadata."""

    hours = parse_preview_limit(request.args.get("hours"), default=24, maximum=720)
    return jsonify({"status": "ok", "hours": hours, "events": list_llm_observability(hours=hours)})


# =========================================================
# SUBJECTS
# =========================================================

@csrf.exempt
@research_bp.route("/api/subjects", methods=["GET"])
@research_bp.route("/api/users", methods=["GET"])
@login_required
@role_required("admin", "researcher", "operator")
@limiter.limit("120 per minute")
def subjects():
    """Return research subjects for the chamber subject selector."""

    connection = db()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            SELECT
                id,
                user_id,
                email,
                subject_id,
                sex,
                age,
                weight,
                notes,
                role,
                is_active,
                created_at
            FROM users
            WHERE is_active = TRUE
              AND role = 'viewer'
              AND email IS NULL
              AND organization_id = %s
            ORDER BY id DESC
        """, (current_user.organization_id,))

        return jsonify([
            {
                "id": row[0],
                "user_id": row[1],
                "email": row[2],
                "subject_id": row[3],
                "sex": row[4],
                "age": row[5],
                "weight": row[6],
                "notes": row[7],
                "role": row[8],
                "is_active": row[9],
                "created_at": str(row[10]) if row[10] else None,
            }
            for row in cursor.fetchall()
        ])

    finally:
        cursor.close()
        connection.close()


@csrf.exempt
@research_bp.route("/api/subjects", methods=["POST"])
@research_bp.route("/api/users", methods=["POST"])
@login_required
@role_required("admin", "researcher", "operator")
@limiter.limit("60 per minute")
def create_subject():
    """Create a subject-only user row from the chamber form."""

    data = request.get_json(silent=True) or {}
    subject_id = clean_value(data.get("subject_id"))

    if not subject_id:
        return error_response("missing subject_id", 400)

    connection = db()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            INSERT INTO users (
                user_id,
                subject_id,
                sex,
                age,
                weight,
                notes,
                role,
                is_active,
                organization_id,
                location_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            subject_id,
            subject_id,
            clean_value(data.get("sex")) or None,
            data.get("age") or None,
            data.get("weight") or None,
            clean_value(data.get("notes")) or None,
            "viewer",
            True,
            current_user.organization_id,
            current_user.location_id,
        ))

        record_audit_event(
            cursor,
            actor_user_id=current_user_id(),
            actor_role=current_user.role,
            action="client.create",
            entity_type="client",
            entity_id=subject_id,
            client_id=subject_id,
            **audit_request_metadata(),
        )
        connection.commit()

        return jsonify({
            "status": "ok",
            "user_id": subject_id,
            "subject_id": subject_id,
        }), 201

    except IntegrityError:
        connection.rollback()
        return error_response("Subject already exists", 400)

    except Exception as exc:
        connection.rollback()
        traceback.print_exc()
        return error_response(str(exc), 500)

    finally:
        cursor.close()
        connection.close()


@csrf.exempt
@research_bp.route("/api/delete_subject", methods=["POST"])
@research_bp.route("/api/delete_user", methods=["POST"])
@login_required
@role_required("admin", "researcher")
@limiter.limit("30 per minute")
def delete_subject():
    """Delete one subject and its related research data."""

    data = request.get_json(silent=True) or {}
    user_id = clean_value(data.get("user_id"))

    if not user_id:
        return error_response("missing user_id", 400)

    connection = db()
    cursor = connection.cursor()

    try:
        deletion_token = (
            "deleted:"
            + hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:16]
        )
        session_ids = collect_subject_session_ids(
            cursor,
            user_id=user_id,
        )

        delete_subject_related_rows(
            cursor,
            user_id=user_id,
            session_ids=session_ids,
        )

        cursor.execute(
            """
            DELETE FROM users
            WHERE user_id = %s
              AND role = 'viewer'
            """,
            (user_id,),
        )

        deleted_subjects = cursor.rowcount

        cursor.execute(
            """
            INSERT INTO data_requests (
                client_id,
                request_type,
                requested_by,
                status,
                details_json,
                completed_at
            )
            VALUES (
                %s, 'delete', %s, 'completed',
                %s::jsonb, CURRENT_TIMESTAMP
            )
            """,
            (
                deletion_token,
                current_user_id(),
                '{"method":"hard_delete","identifier_pseudonymized":true}',
            ),
        )
        cursor.execute(
            """
            UPDATE audit_log
            SET
                client_id = %s,
                entity_id = CASE
                    WHEN entity_type = 'client' THEN %s
                    ELSE entity_id
                END
            WHERE client_id = %s
               OR (entity_type = 'client' AND entity_id = %s)
            """,
            (
                deletion_token,
                deletion_token,
                user_id,
                user_id,
            ),
        )
        record_audit_event(
            cursor,
            actor_user_id=current_user_id(),
            actor_role=current_user.role,
            action="client.delete",
            entity_type="client",
            entity_id=deletion_token,
            client_id=deletion_token,
            details={
                "deleted_sessions": len(session_ids),
                "identifier_pseudonymized": True,
            },
            **audit_request_metadata(),
        )
        connection.commit()

        return jsonify({
            "status": "ok",
            "user_id": user_id,
            "deleted_subjects": deleted_subjects,
            "deleted_sessions": len(session_ids),
        })

    except Exception as exc:
        connection.rollback()
        traceback.print_exc()
        return error_response(str(exc), 500)

    finally:
        cursor.close()
        connection.close()


@research_bp.route("/api/clients/<client_id>/export", methods=["GET"])
@login_required
@role_required("admin", "researcher")
@limiter.limit("10 per hour")
def export_client(client_id: str):
    """Export all client-owned records as a portable JSON ZIP."""

    normalized_client_id = clean_value(client_id)

    if not normalized_client_id:
        return error_response("missing client_id", 400)

    connection = db()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT 1
            FROM users
            WHERE user_id = %s
              AND role = 'viewer'
            """,
            (normalized_client_id,),
        )
        if not cursor.fetchone():
            return error_response("client not found", 404)

        archive = build_client_export(
            cursor,
            client_id=normalized_client_id,
        )
        cursor.execute(
            """
            INSERT INTO data_requests (
                client_id,
                request_type,
                requested_by,
                status,
                details_json,
                completed_at
            )
            VALUES (
                %s, 'export', %s, 'completed',
                '{"format":"zip_json"}'::jsonb,
                CURRENT_TIMESTAMP
            )
            """,
            (
                normalized_client_id,
                current_user_id(),
            ),
        )
        record_audit_event(
            cursor,
            actor_user_id=current_user_id(),
            actor_role=current_user.role,
            action="client.export",
            entity_type="client",
            entity_id=normalized_client_id,
            client_id=normalized_client_id,
            details={"format": "zip_json"},
            **audit_request_metadata(),
        )
        connection.commit()

        safe_client_id = "".join(
            character
            for character in normalized_client_id
            if character.isalnum() or character in {"-", "_"}
        ) or "client"

        return send_file(
            archive,
            mimetype="application/zip",
            as_attachment=True,
            download_name=f"corelabtech_{safe_client_id}_export.zip",
        )
    except Exception as exc:
        connection.rollback()
        traceback.print_exc()
        return error_response(str(exc), 500)
    finally:
        cursor.close()
        connection.close()


# =========================================================
# FIT UPLOAD
# =========================================================

@csrf.exempt
@research_bp.route(
    "/upload_fit",
    methods=["POST"],
)
@login_required
@role_required(
    "admin",
    "researcher",
    "operator",
)
@limiter.limit(UPLOAD_LIMIT)
def upload_fit():
    """Accept a FIT upload and store validated wearable telemetry."""

    file = request.files.get("file")

    session_id = clean_value(
        request.form.get("session_id")
    )

    user_id = clean_value(
        request.form.get("client_id")
        or request.form.get("user_id")
    ) or None

    if not file or not session_id:
        return error_response(
            "missing file or session_id",
            400,
        )

    if not validate_extension(
        file.filename,
        {"fit"},
    ):
        return error_response(
            "invalid FIT extension",
            400,
        )

    if not validate_file_size(
        file,
        100 * 1024 * 1024,
    ):
        return error_response(
            "FIT file too large",
            400,
        )

    filename = safe_upload_filename(
        file.filename.lower()
    )

    temp_path = create_temp_path(filename)

    try:
        file.save(temp_path)

        result = import_fit_file(
            path=temp_path,
            filename=filename,
            session_id=session_id,
            user_id=user_id,
            source_timezone=clean_value(
                request.form.get("source_timezone")
            ) or "UTC",
            device_model=clean_value(request.form.get("device_model")) or None,
        )

        payload = result.to_dict()

        return jsonify({
            "status": "fit_saved",
            "records": payload.get("records_saved", 0),
            "client_id": payload.get("user_id"),
            **payload,
        }), 201

    except DuplicateImportError as exc:
        return jsonify({
            "status": "duplicate",
            "error": str(exc),
            "import_type": exc.import_type,
            "import_id": exc.import_id,
            "records": exc.records_saved,
            "records_saved": exc.records_saved,
        }), 409

    except DataIngestionError as exc:
        return error_response(str(exc), 400)

    except Exception as exc:
        traceback.print_exc()
        return error_response(str(exc), 500)

    finally:
        remove_temp_file(temp_path)


# =========================================================
# CSV UPLOAD
# =========================================================

@csrf.exempt
@research_bp.route(
    "/upload_csv",
    methods=["POST"],
)
@login_required
@role_required(
    "admin",
    "researcher",
    "operator",
)
@limiter.limit(UPLOAD_LIMIT)
def upload_csv():
    """Accept a CSV upload and store validated pulse oximeter telemetry."""

    file = request.files.get("file")

    session_id = clean_value(
        request.form.get("session_id")
    )

    user_id = clean_value(
        request.form.get("client_id")
        or request.form.get("user_id")
    ) or None

    if not file or not session_id:
        return error_response(
            "missing file or session_id",
            400,
        )

    if not validate_extension(
        file.filename,
        {"csv"},
    ):
        return error_response(
            "invalid CSV extension",
            400,
        )

    if not validate_file_size(
        file,
        20 * 1024 * 1024,
    ):
        return error_response(
            "CSV file too large",
            400,
        )

    filename = safe_upload_filename(
        file.filename.lower()
    )

    temp_path = create_temp_path(filename)

    try:
        file.save(temp_path)

        result = import_csv_file(
            path=temp_path,
            filename=filename,
            session_id=session_id,
            user_id=user_id,
            source_timezone=clean_value(
                request.form.get("source_timezone")
            ) or None,
        )

        payload = result.to_dict()

        return jsonify({
            "status": "csv_saved",
            "records": payload.get("records_saved", 0),
            "client_id": payload.get("user_id"),
            **payload,
        }), 201

    except DuplicateImportError as exc:
        return jsonify({
            "status": "duplicate",
            "error": str(exc),
            "import_type": exc.import_type,
            "import_id": exc.import_id,
            "records": exc.records_saved,
            "records_saved": exc.records_saved,
        }), 409

    except DataIngestionError as exc:
        return error_response(str(exc), 400)

    except Exception as exc:
        traceback.print_exc()
        return error_response(str(exc), 500)

    finally:
        remove_temp_file(temp_path)


# =========================================================
# EXTERNAL TELEMETRY UPLOADS
# =========================================================

@csrf.exempt
@research_bp.route("/api/telemetry/preflight", methods=["POST"])
@login_required
@role_required("admin", "researcher", "operator")
@limiter.limit(UPLOAD_LIMIT)
def preflight_telemetry_upload():
    """Validate and summarize a telemetry file before it is persisted."""

    file = request.files.get("file")
    import_type = clean_value(request.form.get("import_type")).lower()
    supported = {
        "fit": ({"fit"}, 100 * 1024 * 1024),
        "csv": ({"csv"}, 20 * 1024 * 1024),
        "polar_csv": ({"csv"}, 100 * 1024 * 1024),
        "apple_health_xml": ({"xml"}, 100 * 1024 * 1024),
        "health_connect_json": ({"json"}, 100 * 1024 * 1024),
    }
    if import_type not in supported:
        return error_response("unsupported telemetry import_type", 400)
    if not file:
        return error_response("missing file", 400)
    extensions, max_size = supported[import_type]
    if not validate_extension(file.filename, extensions):
        return error_response("invalid file extension", 400)
    if not validate_file_size(file, max_size):
        return error_response("file too large", 400)

    filename = safe_upload_filename(file.filename.lower())
    temp_path = create_temp_path(filename)
    try:
        file.save(temp_path)
        preview = preview_telemetry_file(
            path=temp_path,
            import_type=import_type,
            source_timezone=clean_value(request.form.get("source_timezone")) or None,
            device_model=clean_value(request.form.get("device_model")) or None,
        )
        return jsonify(preview)
    except DataIngestionError as exc:
        return error_response(str(exc), 400)
    except Exception as exc:
        return error_response(f"telemetry preflight failed: {exc}", 400)
    finally:
        remove_temp_file(temp_path)


@research_bp.route("/api/sessions/<session_id>/data-sources")
@login_required
@role_required("viewer", "operator", "researcher", "admin")
@limiter.limit(PERF_LIMIT)
def session_data_sources(session_id: str):
    """Show the auditable telemetry sources already imported for a session."""

    user_id = clean_value(request.args.get("client_id"))
    if not user_id:
        return error_response("missing client_id", 400)
    if not can_access_client_record(
        requesting_role=current_user.role,
        requesting_user_id=current_user.user_id,
        client_id=user_id,
        requesting_organization_id=current_user.organization_id,
    ):
        return error_response("forbidden", 403)
    connection = db()
    cursor = connection.cursor()
    try:
        sources = list_session_data_sources(
            cursor, session_id=session_id, user_id=user_id
        )
    finally:
        cursor.close()
        connection.close()
    return jsonify({"status": "ok", "session_id": session_id, "sources": sources})

@csrf.exempt
@research_bp.route("/upload_telemetry", methods=["POST"])
@login_required
@role_required("admin", "researcher", "operator")
@limiter.limit(UPLOAD_LIMIT)
def upload_external_telemetry():
    """Import supported Polar, Apple Health, or Health Connect exports."""

    file = request.files.get("file")
    session_id = clean_value(request.form.get("session_id"))
    user_id = clean_value(
        request.form.get("client_id") or request.form.get("user_id")
    ) or None
    import_type = clean_value(request.form.get("import_type")).lower()
    supported = {
        "polar_csv": {"csv"},
        "apple_health_xml": {"xml"},
        "health_connect_json": {"json"},
    }
    if import_type not in supported:
        return error_response("unsupported telemetry import_type", 400)
    validation_error = validate_upload_request(
        file=file,
        session_id=session_id,
        allowed_extensions=supported[import_type],
        max_size=100 * 1024 * 1024,
    )
    if validation_error:
        return validation_error

    filename = safe_upload_filename(file.filename.lower())
    temp_path = create_temp_path(filename)
    try:
        file.save(temp_path)
        result = import_external_telemetry_file(
            path=temp_path,
            filename=filename,
            session_id=session_id,
            user_id=user_id,
            import_type=import_type,
            source_timezone=clean_value(request.form.get("source_timezone")) or None,
            device_model=clean_value(request.form.get("device_model")) or None,
        )
        payload = result.to_dict()
        return jsonify({
            "status": "telemetry_saved",
            "records": payload.get("records_saved", 0),
            "client_id": payload.get("user_id"),
            **payload,
        }), 201
    except DuplicateImportError as exc:
        return jsonify({
            "status": "duplicate",
            "error": str(exc),
            "import_type": exc.import_type,
            "import_id": exc.import_id,
            "records": exc.records_saved,
            "records_saved": exc.records_saved,
        }), 409
    except DataIngestionError as exc:
        return error_response(str(exc), 400)
    except Exception as exc:
        traceback.print_exc()
        return error_response(str(exc), 500)
    finally:
        remove_temp_file(temp_path)


# =========================================================
# RAW FIT
# =========================================================

@research_bp.route("/api/fit_data")
@login_required
@limiter.limit(PERF_LIMIT)
def fit_data():
    """Return raw FIT data for table/chart previews."""

    session_id = clean_value(
        request.args.get("session_id")
    )

    if not session_id:
        return error_response(
            "missing session_id",
            400,
        )

    connection = db()
    cursor = connection.cursor()
    limit = parse_preview_limit(
        request.args.get("limit")
    )
    import_id = parse_optional_int(
        request.args.get("import_id")
    )

    try:
        return jsonify(
            load_fit(
                cursor,
                session_id=session_id,
                import_id=import_id,
                limit=limit,
            )
        )

    finally:
        cursor.close()
        connection.close()

# =========================================================
# RAW CSV
# =========================================================

@research_bp.route("/api/csv_data")
@login_required
@limiter.limit(PERF_LIMIT)
def csv_data():
    """Return raw CSV data for table/chart previews."""

    session_id = clean_value(
        request.args.get("session_id")
    )

    if not session_id:
        return error_response(
            "missing session_id",
            400,
        )

    connection = db()
    cursor = connection.cursor()
    limit = parse_preview_limit(
        request.args.get("limit")
    )
    import_id = parse_optional_int(
        request.args.get("import_id")
    )

    try:
        return jsonify(
            load_csv(
                cursor,
                session_id=session_id,
                import_id=import_id,
                limit=limit,
            )
        )

    finally:
        cursor.close()
        connection.close()


@research_bp.route("/api/fit_timeseries/<session_id>")
@login_required
@limiter.limit(PERF_LIMIT)
def fit_timeseries(session_id):
    """Return FIT data in chart-friendly arrays."""

    session_id = clean_value(session_id)

    if not session_id:
        return error_response(
            "missing session_id",
            400,
        )

    limit = parse_preview_limit(
        request.args.get("limit"),
        default=1000,
    )
    import_id = parse_optional_int(
        request.args.get("import_id")
    )

    connection = db()
    cursor = connection.cursor()

    try:
        rows = load_fit(
            cursor,
            session_id=session_id,
            import_id=import_id,
            limit=limit,
        )

        return jsonify({
            "time": [
                row.get("timestamp") or row.get("time")
                for row in rows
            ],
            "pulse": [
                row.get("pulse_rate_bpm") or row.get("pulse")
                for row in rows
            ],
            "heart_rate": [
                row.get("heart_rate_bpm") or row.get("heart_rate")
                for row in rows
            ],
            "provenance": [
                {
                    "device_type": row.get("device_type"),
                    "measurement_method": row.get("measurement_method"),
                    "signal_quality": row.get("signal_quality"),
                }
                for row in rows
            ],
            "spo2": [
                row.get("spo2")
                for row in rows
            ],
            "hrv": [
                row.get("hrv")
                for row in rows
            ],
            "limit": limit,
            "records": len(rows),
        })

    finally:
        cursor.close()
        connection.close()


# =========================================================
# MERGE
# =========================================================

@csrf.exempt
@research_bp.route(
    "/api/during_merge",
    methods=["POST"],
)
@login_required
@role_required(
    "operator",
    "researcher",
    "admin",
)
@limiter.limit("60 per hour")
def during_merge():
    """Run the FIT/CSV synchronization step for the DURING phase."""

    data = request.get_json(silent=True) or {}

    session_id = clean_value(
        data.get("session_id")
    )

    if not session_id:
        return error_response(
            "missing session_id",
            400,
        )

    try:
        result = merge_session_data(
            session_id=session_id,
            user_id=clean_value(
                data.get("client_id")
                or data.get("user_id")
            ) or None,
            tolerance_ms=int(
                data.get("tolerance_ms", 2500)
            ),
        )

        connection = db()
        cursor = connection.cursor()

        try:
            merged_rows = load_merged_measurements(
                cursor,
                merge_id=result.merge_id,
                limit=parse_preview_limit(
                    data.get("limit"),
                    default=MAX_PREVIEW_LIMIT,
                ),
            )

        finally:
            cursor.close()
            connection.close()

        return jsonify({
            "status": "ok",
            "result_status": "merge_completed",
            "client_id": result.user_id,
            "mode": result.mode,
            "fit_samples": result.fit_records,
            "csv_samples": result.csv_records,
            "merged": merged_rows,
            **result.to_dict(),
        }), 201

    except MergeInputMissingError as exc:
        return error_response(str(exc), 409)

    except Exception as exc:
        traceback.print_exc()
        return error_response(str(exc), 500)


# =========================================================
# MERGE DATA
# =========================================================

@research_bp.route(
    "/api/merged_data/<session_id>",
)
@login_required
@limiter.limit(PERF_LIMIT)
def merged_data(session_id: str):
    """Return the latest completed merged timeline for a session."""

    connection = db()
    cursor = connection.cursor()
    limit = parse_preview_limit(
        request.args.get("limit")
    )

    try:
        merge_job = get_latest_completed_merge_job(
            cursor,
            session_id=session_id,
        )

        if not merge_job:
            return error_response(
                "No completed merge found",
                404,
            )

        rows = load_merged_measurements(
            cursor,
            merge_id=merge_job["merge_id"],
            limit=limit,
        )

        return jsonify({
            "status": "ok",
            "merge": merge_job,
            "records": len(rows),
            "data": rows,
        })

    finally:
        cursor.close()
        connection.close()

# =========================================================
# SESSION PHASES
# =========================================================

@csrf.exempt
@research_bp.route(
    "/api/save_phase",
    methods=["POST"],
)
@login_required
@role_required(
    "admin",
    "researcher",
    "operator",
)
@limiter.limit("120 per minute")
def save_phase():
    """Save one PRE, DURING or POST phase payload."""

    data = request.get_json(silent=True) or {}
    if data.get("client_id") and not data.get("user_id"):
        data["user_id"] = data["client_id"]

    try:
        result = save_session_phase(
            payload=data,
            initiated_by=get_current_user_id(),
        )

        return jsonify({
            "status": "saved",
            "phase_id": result.phase_id,
            "session_id": result.session_id,
            "phase": result.phase,
            "client_id": data.get("user_id"),
        }), 201

    except ValueError as exc:
        return error_response(str(exc), 400)

    except Exception as exc:
        traceback.print_exc()
        return error_response(str(exc), 500)


@csrf.exempt
@research_bp.route(
    "/api/sessions/<session_id>/recovery-follow-up",
    methods=["POST"],
)
@login_required
@role_required("viewer", "operator", "researcher", "admin")
@limiter.limit("30 per hour")
def save_recovery_follow_up(session_id: str):
    """Save voluntary post-session wellness context and refresh the report."""

    try:
        payload = normalize_recovery_follow_up_payload(
            request.get_json(silent=True) or {}
        )
    except ValueError as exc:
        return error_response(str(exc), 400)

    connection = db()
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            SELECT user_id
            FROM full_sessions
            WHERE session_id = %s
            LIMIT 1
            """,
            (session_id,),
        )
        row = cursor.fetchone()
        if not row:
            return error_response("session not found", 404)

        client_id = row[0]
        if not can_access_client_record(
            requesting_role=getattr(current_user, "role", "viewer"),
            requesting_user_id=current_user_id(),
            client_id=client_id,
            requesting_organization_id=getattr(current_user, "organization_id", None),
        ):
            return error_response("forbidden", 403)

        follow_up_id = create_recovery_follow_up(
            cursor,
            session_id=session_id,
            user_id=client_id,
            payload=payload,
        )
        connection.commit()
    except Exception as exc:
        connection.rollback()
        return error_response(str(exc), 500)
    finally:
        cursor.close()
        connection.close()

    try:
        analysis = run_session_analysis(
            session_id=session_id,
            user_id=client_id,
        ).to_dict()
        recovery_coach = analysis.get("recovery_coach")
    except AnalysisInputMissingError:
        recovery_coach = {
            "status": "follow_up_recorded_analysis_pending",
            "summary": "Follow-up zapisany. Analiza sesji nie jest jeszcze dostepna.",
        }

    return jsonify({
        "status": "saved",
        "follow_up_id": follow_up_id,
        "recovery_coach": recovery_coach,
    }), 201


@csrf.exempt
@research_bp.route(
    "/api/save_full_session",
    methods=["POST"],
)
@login_required
@role_required(
    "admin",
    "researcher",
    "operator",
)
@limiter.limit("60 per minute")
def save_full_session():
    """Persist the full research session after all phases are saved."""

    data = request.get_json(silent=True) or {}

    session_id = clean_value(
        data.get("session_id")
    )
    user_id = clean_value(
        data.get("client_id")
        or data.get("user_id")
    )

    if not session_id:
        return error_response(
            "missing session_id",
            400,
        )

    if not user_id:
        return error_response(
            "missing user_id",
            400,
        )

    pre = data.get("pre") or {}
    wellness_consent = pre.get("wellness_consent") or {}

    if wellness_consent.get("accepted") is not True:
        return error_response(
            "wellness client acknowledgement is required",
            400,
        )

    pre = {
        **pre,
        "wellness_consent": {
            "accepted": True,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "recorded_by": get_current_user_id(),
            "terms_version": "2026-07-26",
        },
    }

    try:
        result = complete_session(
            session_id=session_id,
            user_id=user_id,
            pre=pre,
            during=data.get("during") or {},
            post=data.get("post") or {},
            initiated_by=get_current_user_id(),
        )
        record_session_consent_and_audit(
            session_id=result.session_id,
            client_id=result.user_id,
            consent=pre["wellness_consent"],
        )

        return jsonify({
            "status": "ok",
            "session_id": result.session_id,
            "user_id": result.user_id,
            "client_id": result.user_id,
            "saved_count": 1,
            "fit_samples": result.fit_samples,
            "csv_samples": result.csv_samples,
            "merged_samples": result.merged_samples,
            "features": result.features,
            "completed": True,
        })

    except ValueError as exc:
        return error_response(str(exc), 400)

    except Exception as exc:
        traceback.print_exc()
        return error_response(str(exc), 500)


# =========================================================
# SESSIONS
# =========================================================

@research_bp.route("/api/sessions")
@login_required
@limiter.limit(PERF_LIMIT)
def sessions():
    """List sessions available to the authenticated user."""

    started_at = time.perf_counter()
    try:
        limit = parse_preview_limit(
            request.args.get("limit"),
            default=100,
            maximum=200,
        )
        rows = list_research_sessions(
            requesting_user_id=get_current_user_id(),
            requesting_role=current_user.role,
            requesting_organization_id=current_user.organization_id,
            limit=limit,
        )

        response = jsonify({
            "status": "ok",
            "count": len(rows),
            "limit": limit,
            "sessions": rows,
        })
        response.headers["X-Session-List-Ms"] = str(
            round((time.perf_counter() - started_at) * 1000)
        )
        return response

    except Exception as exc:
        traceback.print_exc()
        return error_response(str(exc), 500)


@research_bp.route(
    "/api/sessions/<session_id>",
)
@login_required
@role_required(
    "viewer",
    "operator",
    "researcher",
    "admin",
)
def get_session(session_id: str):
    """Return one session if the user has permission to see it."""

    result = get_research_session(
        session_id=session_id,
        requesting_user_id=get_current_user_id(),
        requesting_role=current_user.role,
        requesting_organization_id=current_user.organization_id,
    )

    if not result:
        return error_response(
            "session not found",
            404,
        )

    return jsonify(result)


@research_bp.route(
    "/api/session_traceability/<session_id>",
)
@login_required
@role_required(
    "viewer",
    "operator",
    "researcher",
    "admin",
)
@limiter.limit(PERF_LIMIT)
def session_traceability(session_id: str):
    """Return an operational trace for one session without physiology payloads."""

    normalized_session_id = clean_value(session_id)

    if not normalized_session_id:
        return error_response("missing session_id", 400)

    session = get_research_session(
        session_id=normalized_session_id,
        requesting_user_id=get_current_user_id(),
        requesting_role=current_user.role,
        requesting_organization_id=current_user.organization_id,
    )

    if not session:
        return error_response("session not found", 404)

    try:
        return jsonify(get_session_traceability(session=session))

    except Exception as exc:
        traceback.print_exc()
        return error_response(str(exc), 500)


@csrf.exempt
@research_bp.route(
    "/api/delete_sessions",
    methods=["POST"],
)
@login_required
@role_required("admin")
@limiter.limit("30 per minute")
def delete_sessions():
    """Delete selected completed sessions from the dashboard."""

    data = request.get_json(silent=True) or {}
    session_ids = data.get("sessions") or []

    if not session_ids:
        return error_response(
            "missing sessions",
            400,
        )

    try:
        deleted = delete_research_sessions(
            session_ids=session_ids,
        )

        return jsonify({
            "status": "deleted",
            "deleted": deleted,
        })

    except Exception as exc:
        traceback.print_exc()
        return error_response(str(exc), 500)


# =========================================================
# AI ANALYSIS
# =========================================================

@csrf.exempt
@research_bp.route(
    "/api/run_analysis",
    methods=["POST"],
)
@login_required
@role_required(
    "operator",
    "researcher",
    "admin",
)
@limiter.limit("60 per hour")
def run_analysis():
    """Run deterministic AI analysis for one merged session."""

    data = request.get_json(silent=True) or {}

    session_id = clean_value(
        data.get("session_id")
    )

    if not session_id:
        return error_response(
            "missing session_id",
            400,
        )

    try:
        analysis = run_session_analysis(
            session_id=session_id,
        )

        result = {
            **analysis.result,
        }

        score = result.get("overall_score")

        result.setdefault(
            "score",
            score,
        )

        result.setdefault(
            "anomaly",
            bool(result.get("anomaly_detected")),
        )

        result.setdefault(
            "risk_level",
            risk_level_from_score(score),
        )
        write_audit_event(
            action="session.analyze",
            entity_type="session",
            entity_id=analysis.session_id,
            client_id=result.get("client_id"),
            session_id=analysis.session_id,
            details={
                "analysis_id": analysis.ai_result_id,
                "protocol_id": (
                    result.get("protocol") or {}
                ).get("protocol_id"),
            },
        )

        return jsonify({
            "status": "completed",
            "analysis_id": analysis.ai_result_id,
            "session_id": analysis.session_id,
            "client_id": result.get("client_id"),
            "merge_id": analysis.merge_id,
            **result,
        }), 201

    except AnalysisInputMissingError as exc:
        return error_response(str(exc), 422)

    except Exception as exc:
        traceback.print_exc()
        return error_response(str(exc), 500)


# =========================================================
# AI
# =========================================================

@research_bp.route(
    "/api/analysis/<session_id>/latest",
)
@login_required
@role_required("viewer", "operator", "researcher", "admin")
@limiter.limit(PERF_LIMIT)
def latest_analysis(session_id: str):
    """Return the newest analysis result for a session."""

    connection = db()
    cursor = connection.cursor()

    try:
        result = get_latest_ai_result(
            cursor,
            session_id=session_id,
        )

        if not result:
            return error_response(
                "AI result not found",
                404,
            )

        if not can_access_client_record(
            requesting_role=getattr(current_user, "role", "viewer"),
            requesting_user_id=current_user_id(),
            client_id=result.get("user_id"),
            requesting_organization_id=getattr(current_user, "organization_id", None),
        ):
            return error_response("forbidden", 403)

        timeline_sample = request.args.get(
            "timeline_sample",
            type=int,
        )

        if timeline_sample and timeline_sample > 1:
            analysis_result = result.get("result") or {}
            timeline = analysis_result.get("timeline")

            if isinstance(timeline, list) and len(timeline) > timeline_sample:
                last_index = len(timeline) - 1
                sampled_timeline = [
                    timeline[
                        round(i * last_index / (timeline_sample - 1))
                    ]
                    for i in range(timeline_sample)
                ]

                result["timeline_total"] = len(timeline)
                result["timeline_sampled"] = len(sampled_timeline)
                result["result"] = {
                    **analysis_result,
                    "timeline": sampled_timeline,
                    "timeline_total": len(timeline),
                    "timeline_sampled": len(sampled_timeline),
                }

        return jsonify({
            "status": "ok",
            **result,
        })

    finally:
        cursor.close()
        connection.close()


@research_bp.route(
    "/api/analysis/<session_id>/operator-report",
)
@login_required
@role_required("operator", "researcher", "admin")
@limiter.limit(PERF_LIMIT)
def operator_report(session_id: str):
    """Return the constrained operational report without wellness narration."""

    connection = db()
    cursor = connection.cursor()
    try:
        result = get_latest_ai_result(cursor, session_id=session_id)
        if not result:
            return error_response("AI result not found", 404)
        if not can_access_client_record(
            requesting_role=current_user.role,
            requesting_user_id=current_user_id(),
            client_id=result.get("user_id"),
            requesting_organization_id=current_user.organization_id,
        ):
            return error_response("forbidden", 403)
        report = (result.get("result") or {}).get("operator_report")
        if not report:
            return error_response("operator report not found", 404)
        return jsonify({
            "status": "ok",
            "session_id": session_id,
            "operator_report": report,
        })
    finally:
        cursor.close()
        connection.close()


@research_bp.route(
    "/api/analysis/<session_id>/research-summary",
)
@login_required
@role_required("researcher", "admin")
@limiter.limit("60 per hour")
def research_summary(session_id: str):
    """Return a reproducible research view for one authorized session."""

    connection = db()
    cursor = connection.cursor()
    try:
        result = get_latest_ai_result(cursor, session_id=session_id)
        if not result:
            return error_response("AI result not found", 404)
        if not can_access_client_record(
            requesting_role=current_user.role,
            requesting_user_id=current_user_id(),
            client_id=result.get("user_id"),
            requesting_organization_id=current_user.organization_id,
        ):
            return error_response("forbidden", 403)
        analysis = result.get("result") or {}
        research_input = {
            **analysis,
            "model_name": analysis.get("model_name") or result.get("model_name"),
            "model_version": analysis.get("model_version") or result.get("model_version"),
        }
        return jsonify({
            "status": "ok",
            "session_id": session_id,
            "research_summary": build_research_summary(research_input),
        })
    finally:
        cursor.close()
        connection.close()


@research_bp.route(
    "/api/user_trends/<user_id>",
)
@login_required
@limiter.limit(PERF_LIMIT)
def user_trends(user_id: str):
    """Return longitudinal AI trend data for one research subject."""

    subject_id = clean_value(user_id)

    if not subject_id:
        return error_response(
            "missing user_id",
            400,
        )

    try:
        if not can_access_client_record(
            requesting_role=current_user.role,
            requesting_user_id=get_current_user_id(),
            client_id=subject_id,
            requesting_organization_id=current_user.organization_id,
        ):
            return error_response(
                "forbidden",
                403,
            )

        protocol_id = parse_optional_int(
            request.args.get("protocol_id")
        )
        trend_limit = parse_preview_limit(
            request.args.get("limit"),
            default=25,
            maximum=100,
        )
        series = get_user_series_trends(
            user_id=subject_id,
            protocol_id=protocol_id,
            trend_limit=trend_limit,
        )
        return jsonify({
            **series,
            "trend_ai": build_trend_ai_view(series),
        })

    except Exception as exc:
        traceback.print_exc()
        return error_response(str(exc), 500)


@csrf.exempt
@research_bp.route(
    "/api/user_trends/<user_id>/narration",
    methods=["POST"],
)
@login_required
@role_required("viewer", "operator", "researcher", "admin")
@limiter.limit("10 per hour")
def user_trend_narration(user_id: str):
    """Generate an explicitly requested LLM narration over verified trend facts."""

    subject_id = clean_value(user_id)
    if not subject_id:
        return error_response("missing user_id", 400)
    if not can_access_client_record(
        requesting_role=current_user.role,
        requesting_user_id=get_current_user_id(),
        client_id=subject_id,
        requesting_organization_id=current_user.organization_id,
    ):
        return error_response("forbidden", 403)
    try:
        series = get_user_series_trends(
            user_id=subject_id,
            protocol_id=parse_optional_int(request.args.get("protocol_id")),
            trend_limit=parse_preview_limit(request.args.get("limit"), default=25, maximum=100),
        )
        return jsonify({
            "status": "ok",
            "trend_ai": build_trend_ai_view(series, allow_llm=True),
        })
    except Exception as exc:
        traceback.print_exc()
        return error_response(str(exc), 500)


@research_bp.route(
    "/api/wellness/summary/<user_id>",
)
@login_required
@limiter.limit(PERF_LIMIT)
def wellness_summary(user_id: str):
    """Return mobile-friendly wellness status, baseline and recent sessions."""

    subject_id = clean_value(user_id)

    if not subject_id:
        return error_response(
            "missing user_id",
            400,
        )

    connection = db()
    cursor = connection.cursor()

    try:
        if not can_access_client_record(
            requesting_role=current_user.role,
            requesting_user_id=get_current_user_id(),
            client_id=subject_id,
            requesting_organization_id=current_user.organization_id,
        ):
            return error_response(
                "forbidden",
                403,
            )

        return jsonify({
            "status": "ok",
            **get_wellness_summary(
                cursor,
                user_id=subject_id,
                protocol_id=parse_optional_int(
                    request.args.get("protocol_id")
                ),
            ),
        })

    except Exception as exc:
        traceback.print_exc()
        return error_response(str(exc), 500)

    finally:
        cursor.close()
        connection.close()


@research_bp.route(
    "/api/analysis/<session_id>/history",
)
@login_required
@role_required(
    "viewer",
    "operator",
    "researcher",
    "admin",
)
def analysis_history(session_id: str):
    """Return all saved analysis runs for a session."""

    connection = db()
    cursor = connection.cursor()

    try:
        analyses = list_analyses(
            cursor,
            session_id=session_id,
        )

        return jsonify({
            "status": "ok",
            "session_id": session_id,
            "count": len(analyses),
            "analyses": analyses,
        })

    finally:
        cursor.close()
        connection.close()


# =========================================================
# REPORT
# =========================================================

@research_bp.route(
    "/report/series/<user_id>",
)
@login_required
@role_required(
    "viewer",
    "operator",
    "researcher",
    "admin",
)
@limiter.limit("20 per hour")
def series_report(user_id: str):
    """Generate and download a PDF report for a client's session series."""

    subject_id = clean_value(user_id)
    started_at = time.perf_counter()

    if not subject_id:
        return error_response("missing user_id", 400)

    try:
        trend_limit = parse_preview_limit(
            request.args.get("limit"),
            default=25,
            maximum=100,
        )
        export = generate_series_report_for_client(
            user_id=subject_id,
            requesting_user_id=get_current_user_id(),
            requesting_role=current_user.role,
            requesting_organization_id=current_user.organization_id,
            protocol_id=parse_optional_int(request.args.get("protocol_id")),
            trend_limit=trend_limit,
        )

        write_audit_event(
            action=export.audit_action,
            entity_type=export.audit_entity_type,
            entity_id=export.audit_entity_id,
            client_id=export.audit_client_id,
            session_id=export.audit_session_id,
            details=export.audit_details,
        )

        response = send_file(
            export.path,
            as_attachment=True,
            download_name=export.download_name,
        )
        response.headers["X-Report-Generation-Ms"] = str(
            round((time.perf_counter() - started_at) * 1000)
        )
        return response

    except PermissionError as exc:
        return error_response(str(exc), 403)

    except Exception as exc:
        traceback.print_exc()
        return error_response(str(exc), 500)


@research_bp.route(
    "/report/<session_id>",
)
@login_required
@role_required(
    "viewer",
    "operator",
    "researcher",
    "admin",
)
@limiter.limit("20 per hour")
def report(session_id: str):
    """Generate and download a PDF report for a session."""

    started_at = time.perf_counter()
    try:
        export = generate_report_for_session(
            session_id=session_id,
            requesting_user_id=get_current_user_id(),
            requesting_role=current_user.role,
            requesting_organization_id=current_user.organization_id,
        )

        write_audit_event(
            action=export.audit_action,
            entity_type=export.audit_entity_type,
            entity_id=export.audit_entity_id,
            client_id=export.audit_client_id,
            session_id=export.audit_session_id,
            details=export.audit_details,
        )

        response = send_file(
            export.path,
            as_attachment=True,
            download_name=export.download_name,
        )
        response.headers["X-Report-Generation-Ms"] = str(
            round((time.perf_counter() - started_at) * 1000)
        )
        return response

    except FileNotFoundError as exc:
        return error_response(str(exc), 404)

    except Exception as exc:
        traceback.print_exc()
        return error_response(str(exc), 500)


# =========================================================
# ADMIN COMPATIBILITY ROUTES
# =========================================================

@csrf.exempt
@research_bp.route("/api/admin/accounts", methods=["GET"])
@login_required
@role_required("admin")
@limiter.limit("120 per minute")
def admin_accounts_list():
    """Return account rows for the admin accounts page."""

    connection = db()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            SELECT user_id, email, role, is_active, created_at
            FROM users
            WHERE email IS NOT NULL
            ORDER BY id ASC
        """)

        return jsonify([
            {
                "user_id": row[0],
                "email": row[1],
                "role": row[2],
                "is_active": row[3],
                "created_at": str(row[4]) if row[4] else None,
            }
            for row in cursor.fetchall()
        ])

    finally:
        cursor.close()
        connection.close()


@csrf.exempt
@research_bp.route("/api/admin/accounts", methods=["POST"])
@login_required
@role_required("admin")
@limiter.limit("30 per minute")
def admin_create_account():
    """Create an authenticated application account."""

    data = request.get_json(silent=True) or {}
    email = clean_value(data.get("email")).lower()
    password = data.get("password") or ""
    role = clean_value(data.get("role")) or "viewer"
    allowed_roles = {"admin", "researcher", "operator", "viewer"}

    if not email:
        return error_response("missing email", 400)

    if not password:
        return error_response("missing password", 400)

    if role not in allowed_roles:
        return error_response("invalid role", 400)

    user_id = email.split("@", 1)[0]
    connection = db()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            INSERT INTO users (
                user_id,
                email,
                subject_id,
                password_hash,
                role,
                is_active
            )
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            user_id,
            email,
            user_id.upper(),
            generate_password_hash(password),
            role,
            True,
        ))

        connection.commit()

        return jsonify({
            "status": "ok",
            "email": email,
            "role": role,
        }), 201

    except IntegrityError:
        connection.rollback()
        return error_response("Account already exists", 400)

    except Exception as exc:
        connection.rollback()
        traceback.print_exc()
        return error_response(str(exc), 500)

    finally:
        cursor.close()
        connection.close()


@csrf.exempt
@research_bp.route("/api/admin/accounts/reset_password", methods=["POST"])
@login_required
@role_required("admin")
@limiter.limit("30 per minute")
def admin_reset_password():
    """Set a new password hash for an existing account."""

    data = request.get_json(silent=True) or {}
    email = clean_value(data.get("email")).lower()
    password = data.get("password") or ""

    if not email:
        return error_response("missing email", 400)

    if not password:
        return error_response("missing password", 400)

    connection = db()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            UPDATE users
            SET password_hash = %s
            WHERE email = %s
        """, (
            generate_password_hash(password),
            email,
        ))

        connection.commit()

        if cursor.rowcount != 1:
            return error_response("account not found", 404)

        return jsonify({
            "status": "ok",
            "email": email,
        })

    except Exception as exc:
        connection.rollback()
        traceback.print_exc()
        return error_response(str(exc), 500)

    finally:
        cursor.close()
        connection.close()


@csrf.exempt
@research_bp.route("/api/admin/accounts/update_role", methods=["POST"])
@login_required
@role_required("admin")
@limiter.limit("30 per minute")
def admin_update_role():
    """Change a user's role, except the current admin's own role."""

    data = request.get_json(silent=True) or {}
    email = clean_value(data.get("email")).lower()
    role = clean_value(data.get("role"))
    allowed_roles = {"admin", "researcher", "operator", "viewer"}
    current_email = clean_value(current_user.email).lower()

    if not email:
        return error_response("missing email", 400)

    if email == current_email:
        return error_response("You cannot change your own role", 400)

    if role not in allowed_roles:
        return error_response("invalid role", 400)

    connection = db()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            UPDATE users
            SET role = %s
            WHERE email = %s
        """, (
            role,
            email,
        ))

        connection.commit()

        if cursor.rowcount != 1:
            return error_response("account not found", 404)

        return jsonify({
            "status": "ok",
            "email": email,
            "role": role,
        })

    except Exception as exc:
        connection.rollback()
        traceback.print_exc()
        return error_response(str(exc), 500)

    finally:
        cursor.close()
        connection.close()


@csrf.exempt
@research_bp.route("/api/admin/accounts/toggle_active", methods=["POST"])
@login_required
@role_required("admin")
@limiter.limit("30 per minute")
def admin_toggle_account_active():
    """Activate or deactivate an account, protecting the current admin."""

    data = request.get_json(silent=True) or {}
    email = clean_value(data.get("email")).lower()
    is_active = bool(data.get("is_active"))
    current_email = clean_value(current_user.email).lower()

    if not email:
        return error_response("missing email", 400)

    if email == current_email and not is_active:
        return error_response(
            "You cannot deactivate your own account",
            400,
        )

    connection = db()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            UPDATE users
            SET is_active = %s
            WHERE email = %s
        """, (
            is_active,
            email,
        ))

        connection.commit()

        if cursor.rowcount != 1:
            return error_response("account not found", 404)

        return jsonify({
            "status": "ok",
            "email": email,
            "is_active": is_active,
        })

    except Exception as exc:
        connection.rollback()
        traceback.print_exc()
        return error_response(str(exc), 500)

    finally:
        cursor.close()
        connection.close()


@research_bp.route("/debug/db")
@login_required
@role_required("admin")
def debug_db():
    """Return lightweight row counts for admin database diagnostics."""

    if os.getenv("DISABLE_DEBUG_ROUTES", "true").lower() == "true":
        abort(404)

    connection = db()
    cursor = connection.cursor()
    result = {}

    try:
        for table in (
            "users",
            "tests",
            "fit_data",
            "csv_data",
            "full_sessions",
        ):
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            result[table] = cursor.fetchone()[0]

        accept = request.headers.get("Accept", "")

        if (
            "text/html" in accept
            and "application/json" not in accept
        ):
            return render_template(
                "debug_db.html",
                tables=result,
            )

        return jsonify({
            "status": "ok",
            "tables": result,
        })

    finally:
        cursor.close()
        connection.close()


# =========================================================
# CONTROLLER HELPERS
# =========================================================

def clean_value(value) -> str:
    return (
        str(value).strip()
        if value is not None
        else ""
    )


def get_current_user_id() -> str | None:
    return (
        getattr(current_user, "user_id", None)
        or getattr(current_user, "email", None)
    )


def risk_level_from_score(score) -> str:
    try:
        numeric_score = float(score)
    except (TypeError, ValueError):
        return "Unknown"

    if numeric_score >= 90:
        return "Low"

    if numeric_score >= 70:
        return "Moderate"

    return "High"


def create_temp_path(
    filename: str,
) -> Path:
    TEMP_UPLOAD_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    return TEMP_UPLOAD_DIRECTORY / (
        f"{uuid.uuid4()}_{filename}"
    )


def remove_temp_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        traceback.print_exc()


def validate_upload_request(
    *,
    file,
    session_id: str,
    allowed_extensions: set[str],
    max_size: int,
):
    if not file or not session_id:
        return error_response(
            "missing file or session_id",
            400,
        )

    if not validate_extension(
        file.filename,
        allowed_extensions,
    ):
        return error_response(
            "invalid file extension",
            400,
        )

    if not validate_file_size(
        file,
        max_size,
    ):
        return error_response(
            "file too large",
            400,
        )

    return None


def table_exists(cursor, table_name: str) -> bool:
    """Check optional migration tables before compatibility deletes use them."""

    cursor.execute(
        "SELECT to_regclass(%s)",
        (f"public.{table_name}",),
    )

    return cursor.fetchone()[0] is not None


def collect_subject_session_ids(
    cursor,
    *,
    user_id: str,
) -> list[str]:
    """Find every session id connected with a subject across known tables."""

    session_ids = set()

    for table in (
        "full_sessions",
        "tests",
        "fit_data",
        "csv_data",
        "fit_imports",
        "csv_imports",
        "merge_jobs",
        "merged_data",
        "ai_results",
        "session_features",
        "hrv_imports",
        "hrv_intervals",
    ):
        if not table_exists(cursor, table):
            continue

        cursor.execute(
            f"""
            SELECT DISTINCT session_id
            FROM {table}
            WHERE user_id = %s
            """,
            (user_id,),
        )

        session_ids.update(
            row[0]
            for row in cursor.fetchall()
            if row[0]
        )

    return sorted(session_ids)


def delete_subject_related_rows(
    cursor,
    *,
    user_id: str,
    session_ids: list[str],
) -> None:
    """Delete subject-owned data while tolerating absent optional tables."""

    tables = (
        "consent_records",
        "recovery_follow_ups",
        "daily_baselines",
        "session_features",
        "hrv_intervals",
        "hrv_imports",
        "ai_results",
        "merged_data",
        "merge_jobs",
        "fit_data",
        "csv_data",
        "tests",
        "full_sessions",
        "client_programs",
        "fit_imports",
        "csv_imports",
    )

    for table in tables:
        if not table_exists(cursor, table):
            continue

        if table in {"daily_baselines", "consent_records", "client_programs"}:
            owner_column = (
                "client_id"
                if table in {"consent_records", "client_programs"}
                else "user_id"
            )
            cursor.execute(
                f"""
                DELETE FROM {table}
                WHERE {owner_column} = %s
                """,
                (user_id,),
            )
        elif session_ids:
            cursor.execute(
                f"""
                DELETE FROM {table}
                WHERE user_id = %s
                OR session_id = ANY(%s)
                """,
                (user_id, session_ids),
            )
        else:
            cursor.execute(
                f"""
                DELETE FROM {table}
                WHERE user_id = %s
                """,
                (user_id,),
            )


def error_response(
    message: str,
    status_code: int,
):
    return jsonify({
        "status": "error",
        "error": message,
    }), status_code
