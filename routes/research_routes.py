# routes/research_routes.py
"""Research-facing Flask routes.

This blueprint serves the chamber workflow, upload APIs, merge/analysis APIs,
admin compatibility endpoints and public research pages.
"""

import os
import traceback
import uuid
from pathlib import Path

from psycopg2 import IntegrityError
from flask import (
    Blueprint,
    jsonify,
    render_template,
    request,
    send_file,
)
from flask_login import current_user, login_required
from werkzeug.security import generate_password_hash

from auth.decorators import role_required
from database_postgres import db

from repositories.analysis_repository import (
    get_latest_ai_result,
    list_analyses,
)

from repositories.data_repository import (
    load_csv,
    load_fit,
)

from repositories.merge_repository import (
    get_latest_completed_merge_job,
    load_merged_measurements,
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
    run_session_analysis,
)

from services.data_ingestion import (
    DataIngestionError,
    DuplicateImportError,
    import_csv_file,
    import_fit_file,
)

from services.data_merge import (
    MergeInputMissingError,
    merge_session_data,
)

from services.session_service import (
    complete_session,
    delete_research_sessions,
    generate_session_report,
    get_research_session,
    list_research_sessions,
    save_session_phase,
)


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
    return render_template(
        "ai_testing_lab_public.html"
    )


@research_bp.route("/performance-tests")
@login_required
@role_required("admin")
def performance_tests():
    return render_template(
        "performance_tests.html"
    )


@research_bp.route("/admin")
@login_required
@role_required("admin")
def admin_panel():
    return render_template(
        "admin_panel.html"
    )


@research_bp.route("/admin/accounts")
@login_required
@role_required("admin")
def admin_accounts():
    return render_template(
        "admin_accounts.html"
    )


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
            ORDER BY id DESC
        """)

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
                is_active
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            subject_id,
            subject_id,
            clean_value(data.get("sex")) or None,
            data.get("age") or None,
            data.get("weight") or None,
            clean_value(data.get("notes")) or None,
            "viewer",
            True,
        ))

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
@role_required("admin", "researcher", "operator")
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
            "DELETE FROM users WHERE user_id = %s",
            (user_id,),
        )

        deleted_subjects = cursor.rowcount
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
        request.form.get("user_id")
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
        )

        payload = result.to_dict()

        return jsonify({
            "status": "fit_saved",
            "records": payload.get("records_saved", 0),
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
        request.form.get("user_id")
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
        )

        payload = result.to_dict()

        return jsonify({
            "status": "csv_saved",
            "records": payload.get("records_saved", 0),
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
                row.get("pulse") or row.get("heart_rate")
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
                data.get("user_id")
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
        }), 201

    except ValueError as exc:
        return error_response(str(exc), 400)

    except Exception as exc:
        traceback.print_exc()
        return error_response(str(exc), 500)


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
        data.get("user_id")
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

    try:
        result = complete_session(
            session_id=session_id,
            user_id=user_id,
            pre=data.get("pre") or {},
            during=data.get("during") or {},
            post=data.get("post") or {},
            initiated_by=get_current_user_id(),
        )

        return jsonify({
            "status": "ok",
            "session_id": result.session_id,
            "user_id": result.user_id,
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

    try:
        rows = list_research_sessions(
            requesting_user_id=get_current_user_id(),
            requesting_role=current_user.role,
        )

        return jsonify({
            "status": "ok",
            "count": len(rows),
            "sessions": rows,
        })

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
    )

    if not result:
        return error_response(
            "session not found",
            404,
        )

    return jsonify(result)


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
            user_id=get_current_user_id(),
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

        return jsonify({
            "status": "completed",
            "analysis_id": analysis.ai_result_id,
            "session_id": analysis.session_id,
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

    connection = db()
    cursor = connection.cursor()

    try:
        if (
            current_user.role not in ("admin", "researcher")
            and subject_id != get_current_user_id()
        ):
            return error_response(
                "forbidden",
                403,
            )

        cursor.execute(
            """
            SELECT
                session_id,
                overall_score,
                data_quality_score,
                anomaly_detected,
                summary,
                features_json,
                created_at
            FROM ai_results
            WHERE user_id = %s
            ORDER BY created_at ASC, ai_result_id ASC
            """,
            (subject_id,),
        )

        analysis_rows = cursor.fetchall()

        analyses = []
        scores = []
        hrv_values = []
        spo2_values = []
        pulse_values = []

        for row in analysis_rows:
            features = row[5] or {}

            score = row[1]
            avg_hrv = pick_feature(
                features,
                "avg_hrv",
            )
            avg_spo2 = pick_feature(
                features,
                "avg_spo2",
                "avg_csv_spo2",
            )
            avg_pulse = pick_feature(
                features,
                "avg_pulse",
                "avg_csv_pulse",
            )

            append_numeric(scores, score)
            append_numeric(hrv_values, avg_hrv)
            append_numeric(spo2_values, avg_spo2)
            append_numeric(pulse_values, avg_pulse)

            analyses.append({
                "session_id": row[0],
                "overall_score": score,
                "data_quality_score": row[2],
                "anomaly_detected": bool(row[3]),
                "summary": row[4],
                "avg_spo2": avg_spo2,
                "avg_pulse": avg_pulse,
                "avg_hrv": avg_hrv,
                "created_at": (
                    row[6].isoformat()
                    if row[6]
                    else None
                ),
            })

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM full_sessions
            WHERE user_id = %s
            """,
            (subject_id,),
        )

        session_count = cursor.fetchone()[0]

        return jsonify({
            "status": "ok",
            "user_id": subject_id,
            "records": len(analyses),
            "session_count": session_count,
            "avg_score": average_or_none(scores),
            "latest_score": scores[-1] if scores else None,
            "avg_spo2": average_or_none(spo2_values),
            "avg_pulse": average_or_none(pulse_values),
            "avg_hrv": average_or_none(hrv_values),
            "anomaly_count": sum(
                1
                for row in analyses
                if row["anomaly_detected"]
            ),
            "trend_direction": calculate_trend_direction(scores),
            "analyses": analyses,
            "timeline": analyses,
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

    try:
        path = generate_session_report(
            session_id=session_id,
            requesting_user_id=get_current_user_id(),
            requesting_role=current_user.role,
        )

        return send_file(
            path,
            as_attachment=True,
            download_name=(
                f"corelabtech_{session_id}_report.pdf"
            ),
        )

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


def pick_feature(
    features: dict,
    *keys: str,
):
    """Return the first non-empty feature value from possible key names."""

    for key in keys:
        value = features.get(key)

        if value is not None:
            return value

    return None


def append_numeric(
    values: list[float],
    value,
) -> None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return

    values.append(numeric)


def average_or_none(
    values: list[float],
) -> float | None:
    if not values:
        return None

    return round(
        sum(values) / len(values),
        2,
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


def calculate_trend_direction(
    scores: list[float],
) -> str:
    if len(scores) < 2:
        return "insufficient_data"

    delta = scores[-1] - scores[0]

    if delta >= 5:
        return "improving"

    if delta <= -5:
        return "declining"

    return "stable"


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
        "ai_results",
        "merged_data",
        "merge_jobs",
        "fit_data",
        "csv_data",
        "tests",
        "full_sessions",
        "fit_imports",
        "csv_imports",
    )

    for table in tables:
        if not table_exists(cursor, table):
            continue

        if session_ids:
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
