from flask_login import login_required, current_user
from auth.decorators import role_required
from flask import Blueprint, render_template, jsonify, request, send_file
from database_postgres import db

from reports.report_generator import generate_report

from ai.anomaly_detection import detect_anomaly
from ai.hbot_prediction import predict_hbot_response
from ai.physiology_ai import analyze_physiology
from ai.explain_engine import explain_anomaly

from services.fit_parser import parse_fit_file
from services.csv_parser import parse_csv_file
from services.ai_engine import run_ai_analysis
from services.test_generator import generate_playwright_test

from core.pipeline.pipeline_runner import run_full_pipeline
from core.qa.playwright_runner import run_playwright_tests

from security.upload_validation import (
    validate_extension,
    safe_upload_filename,
    validate_file_size
)
from flask import send_from_directory
from pathlib import Path

from security.csrf import csrf
from security.limiter import limiter

from psycopg2 import IntegrityError

import os
import uuid
import json
import datetime
import traceback


research_bp = Blueprint("research", __name__)


# =========================================
# PERFORMANCE MODE LIMITS
# =========================================

PERFORMANCE_TESTING = (
    os.getenv("PERFORMANCE_TESTING", "false")
    .lower() == "true"
)

PERF_LIMIT = (
    "5000 per minute"
    if PERFORMANCE_TESTING
    else "300 per minute"
)

UPLOAD_LIMIT = (
    "5000 per minute"
    if PERFORMANCE_TESTING
    else "60 per minute"
)


# =========================================================
# HELPERS
# =========================================================

def avg(values):
    clean = [
        v for v in values
        if v is not None
    ]

    return (
        round(sum(clean) / len(clean), 2)
        if clean
        else None
    )


def calculate_session_score(pre, post, features):

    pre_spo2 = pre.get("spo2")
    post_spo2 = post.get("spo2")
    post_pulse = post.get("pulse")

    score = 100
    reasons = []
    positive_findings = []

    # DURING SpO2
    if features.get("min_spo2") is not None:

        if features["min_spo2"] < 90:
            score -= 40
            reasons.append(
                "DURING SpO2 dropped below 90% - high warning"
            )

        elif features["min_spo2"] < 92:
            score -= 30
            reasons.append(
                "DURING SpO2 dropped to 90-91% - warning"
            )

        elif features["min_spo2"] < 94:
            score -= 15
            reasons.append(
                "DURING SpO2 is borderline low"
            )

    # POST SpO2
    if post_spo2 is not None:

        if post_spo2 < 90:
            score -= 40
            reasons.append(
                "POST SpO2 below 90% - high warning"
            )

        elif post_spo2 < 92:
            score -= 30
            reasons.append(
                "POST SpO2 90-91% - warning"
            )

        elif post_spo2 < 94:
            score -= 15
            reasons.append(
                "POST SpO2 92-93% - borderline"
            )

    # PRE -> POST SpO2 drop
    if pre_spo2 is not None and post_spo2 is not None:

        spo2_drop = pre_spo2 - post_spo2

        if spo2_drop >= 5:
            score -= 25
            reasons.append(
                f"SpO2 dropped by {spo2_drop}% from PRE to POST"
            )

        elif spo2_drop >= 3:
            score -= 10
            reasons.append(
                f"SpO2 dropped by {spo2_drop}% from PRE to POST"
            )

    # HRV
    if (
        features.get("avg_hrv") is not None
        and features["avg_hrv"] < 30
    ):
        score -= 20
        reasons.append(
            "Average HRV is below 30 ms"
        )

    # FIT HR
    if (
        features.get("max_fit_hr") is not None
        and features["max_fit_hr"] > 160
    ):
        score -= 15
        reasons.append(
            "FIT HR exceeded 160 bpm"
        )

    # CSV Pulse
    if (
        features.get("max_csv_pulse") is not None
        and features["max_csv_pulse"] > 160
    ):
        score -= 15
        reasons.append(
            "CSV pulse exceeded 160 bpm"
        )

    # POST Pulse
    if post_pulse is not None and post_pulse > 120:
        score -= 10
        reasons.append(
            "POST pulse is elevated above 120 bpm"
        )

    # Positive findings
    if features.get("avg_csv_spo2") is not None:

        if features["avg_csv_spo2"] >= 97:
            positive_findings.append(
                "Excellent oxygen saturation during session"
            )

        elif features["avg_csv_spo2"] >= 95:
            positive_findings.append(
                "Normal oxygen saturation maintained"
            )

    if post_spo2 is not None:

        if post_spo2 >= 95:
            positive_findings.append(
                "Post-session SpO2 recovered to normal range"
            )

        elif post_spo2 >= 92:
            positive_findings.append(
                "Post-session SpO2 acceptable"
            )

    if (
        features.get("max_fit_hr") is not None
        and features["max_fit_hr"] < 140
    ):
        positive_findings.append(
            "Heart rate response remained stable"
        )

    if (
        features.get("avg_hrv") is not None
        and features["avg_hrv"] >= 40
    ):
        positive_findings.append(
            "HRV indicates good autonomic recovery"
        )

    score = max(score, 0)

    risk_level = (
        "Low"
        if score >= 90
        else "Moderate"
        if score >= 70
        else "High"
    )

    all_messages = []

    if reasons:
        all_messages.extend(reasons)

    if positive_findings:
        all_messages.extend(positive_findings)

    summary = (
        " | ".join(all_messages)
        if all_messages
        else "No significant physiological deviations detected"
    )

    return {
        "score": score,
        "risk_level": risk_level,
        "anomaly": score < 70,
        "reasons": reasons,
        "positive_findings": positive_findings,
        "summary": summary,
    }


# =========================================================
# PAGES
# =========================================================

@research_bp.route("/platform")
def research_platform():
    return render_template("research_platform.html")


@research_bp.route("/research")
@login_required
@role_required("viewer", "operator", "researcher", "admin")
def research_dashboard():
    return render_template("research_dashboard.html")


@research_bp.route("/admin")
@login_required
@role_required("admin")
def admin_panel():
    return render_template("admin_panel.html")


@research_bp.route("/chamber")
@login_required
@role_required("operator", "researcher", "admin")
def chamber_testing():
    return render_template("chamber_testing.html")


@research_bp.route("/performance-tests")
@login_required
@role_required("admin")
def performance_tests():
    return render_template("performance_tests.html")


@research_bp.route("/ai-testing-lab")
def ai_testing_lab_public():
    return render_template("ai_testing_lab_public.html")


# =========================================================
# PERFORMANCE-ONLY SESSIONS
# =========================================================

@research_bp.route("/api/performance/sessions", methods=["GET"])
def performance_sessions():

    if os.getenv("PERFORMANCE_TESTING", "false").lower() != "true":
        return jsonify({
            "status": "error",
            "error": "performance testing disabled"
        }), 403

    con = None

    try:

        con = db()
        c = con.cursor()

        c.execute("""
            SELECT
                session_id,
                COALESCE(user_id, 'UNKNOWN') as user_id,
                completed,
                created_at
            FROM full_sessions
            ORDER BY created_at DESC
        """)

        rows = c.fetchall()

        data = []

        for r in rows:

            data.append({
                "session_id": r[0],
                "user_id": r[1],
                "completed": bool(r[2]),
                "date": r[3].isoformat() if r[3] else None,
            })

        c.close()
        con.close()

        return jsonify({
            "status": "ok",
            "count": len(data),
            "sessions": data
        })

    except Exception as e:

        traceback.print_exc()

        if con:
            con.close()

        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

# =========================================================
# USERS - LIST
# admin + researcher can view users
# =========================================================

@research_bp.route("/api/users", methods=["GET"])
@login_required
@role_required("admin", "researcher")
@limiter.limit("120 per minute")
def users():

    con = None

    try:
        con = db()
        c = con.cursor()

        c.execute("""
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
                is_active
            FROM users
            ORDER BY id DESC
        """)

        rows = c.fetchall()

        c.close()
        con.close()

        return jsonify([
            {
                "id": r[0],
                "user_id": r[1] or str(r[0]),
                "email": r[2],
                "subject_id": r[3],
                "sex": r[4],
                "age": r[5],
                "weight": r[6],
                "notes": r[7],
                "role": r[8],
                "is_active": r[9],
            }
            for r in rows
        ])

    except Exception as e:

        traceback.print_exc()

        if con:
            con.rollback()
            con.close()

        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500


# =========================================================
# USERS - CREATE
# only admin can create users
# =========================================================

@csrf.exempt
@research_bp.route("/api/users", methods=["POST"])
@login_required
@role_required("admin")
@limiter.limit("60 per minute")
def create_user():

    con = None

    try:
        con = db()
        c = con.cursor()

        data = request.get_json() or {}
        user_id = str(uuid.uuid4())[:8]

        c.execute("""
            INSERT INTO users(
                user_id,
                subject_id,
                sex,
                age,
                weight,
                notes,
                role,
                is_active
            )
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            user_id,
            data.get("subject_id"),
            data.get("sex"),
            data.get("age"),
            data.get("weight"),
            data.get("notes"),
            data.get("role", "viewer"),
            True,
        ))

        con.commit()

        c.close()
        con.close()

        return jsonify({
            "status": "ok",
            "user_id": user_id
        })

    except IntegrityError:

        if con:
            con.rollback()
            con.close()

        return jsonify({
            "status": "error",
            "error": "User already exists"
        }), 400

    except Exception as e:

        traceback.print_exc()

        if con:
            con.rollback()
            con.close()

        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500


@csrf.exempt
@research_bp.route("/api/delete_user", methods=["POST"])
@login_required
@role_required("admin")
@limiter.limit("10 per minute")
def delete_user():

    data = request.get_json() or {}
    user_id = data.get("user_id")

    if not user_id:
        return jsonify({
            "error": "missing user_id"
        }), 400

    con = None

    try:

        con = db()
        c = con.cursor()

        c.execute(
            "DELETE FROM tests WHERE user_id=%s",
            (user_id,)
        )

        c.execute(
            "DELETE FROM fit_data WHERE user_id=%s",
            (user_id,)
        )

        c.execute(
            "DELETE FROM csv_data WHERE user_id=%s",
            (user_id,)
        )

        c.execute(
            "DELETE FROM full_sessions WHERE user_id=%s",
            (user_id,)
        )

        c.execute(
            "DELETE FROM users WHERE user_id=%s",
            (user_id,)
        )

        con.commit()

        c.close()
        con.close()

        return jsonify({
            "status": "ok",
            "user_id": user_id
        })

    except Exception as e:

        traceback.print_exc()

        if con:
            con.rollback()
            con.close()

        return jsonify({
            "error": str(e)
        }), 500


# =========================================================
# UPLOAD FIT / CSV RAW
# =========================================================

@csrf.exempt
@research_bp.route("/upload_fit", methods=["POST"])
@login_required
@role_required("operator", "admin")
@limiter.limit(UPLOAD_LIMIT)
def upload_fit():

    file = request.files.get("file")
    session_id = request.form.get("session_id")

    if not file or not session_id:
        return jsonify({
            "error": "missing file or session_id"
        }), 400

    if not validate_extension(file.filename, {"fit"}):
        return jsonify({
            "error": "invalid FIT extension"
        }), 400

    if not validate_file_size(file, 100 * 1024 * 1024):
        return jsonify({
            "error": "FIT file too large"
        }), 400

    user_id = (
        session_id.split("_")[0]
        if "_" in session_id
        else session_id
    )

    filename = safe_upload_filename(
        file.filename.lower()
    )

    os.makedirs(
        "data/uploads/temp",
        exist_ok=True
    )

    temp_path = os.path.join(
        "data/uploads/temp",
        f"{uuid.uuid4()}_{filename}"
    )

    con = None

    try:

        file.save(temp_path)

        rows = parse_fit_file(temp_path)

        print("=" * 50)
        print("FIT PARSED:", len(rows))
        print("SESSION:", session_id)
        print("=" * 50)

        con = db()
        c = con.cursor()

        c.execute("""
            INSERT INTO users (
                user_id,
                subject_id,
                role,
                is_active,
                notes
            )
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO NOTHING
        """, (
            user_id,
            user_id,
            "operator",
            True,
            "Auto-created during FIT upload"
        ))

        for r in rows:

            c.execute("""
                INSERT INTO fit_data (
                    session_id,
                    user_id,
                    timestamp,
                    heart_rate,
                    pulse,
                    hr,
                    spo2,
                    rr_interval,
                    hrv,
                    source,
                    filename,
                    raw_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                session_id,
                user_id,
                str(r.get("timestamp")) if r.get("timestamp") else None,
                r.get("heart_rate"),
                r.get("pulse"),
                r.get("heart_rate") or r.get("pulse"),
                r.get("spo2"),
                r.get("rr_interval"),
                r.get("hrv"),
                r.get("source", "fit"),
                filename,
                json.dumps(r, default=str),
            ))

        con.commit()

        c.close()
        con.close()

        return jsonify({
            "status": "fit_saved",
            "records": len(rows),
            "session_id": session_id,
            "user_id": user_id,
            "file": filename,
        })

    except Exception as e:

        traceback.print_exc()

        if con:
            con.rollback()
            con.close()

        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

    finally:

        if os.path.exists(temp_path):
            os.remove(temp_path)


@csrf.exempt
@research_bp.route("/upload_csv", methods=["POST"])
@login_required
@role_required("operator", "admin")
@limiter.limit(UPLOAD_LIMIT)
def upload_csv():

    file = request.files.get("file")
    session_id = request.form.get("session_id")

    if not file or not session_id:
        return jsonify({
            "error": "missing file or session_id"
        }), 400

    if not validate_extension(file.filename, {"csv"}):
        return jsonify({
            "error": "invalid CSV extension"
        }), 400

    if not validate_file_size(file, 20 * 1024 * 1024):
        return jsonify({
            "error": "CSV file too large"
        }), 400

    user_id = (
        session_id.split("_")[0]
        if "_" in session_id
        else session_id
    )

    filename = safe_upload_filename(
        file.filename.lower()
    )

    os.makedirs(
        "data/uploads/temp",
        exist_ok=True
    )

    temp_path = os.path.join(
        "data/uploads/temp",
        f"{uuid.uuid4()}_{filename}"
    )

    con = None

    try:

        file.save(temp_path)

        rows = parse_csv_file(temp_path)

        print("=" * 50)
        print("CSV PARSED:", len(rows))
        print("SESSION:", session_id)
        print("=" * 50)

        con = db()
        c = con.cursor()

        c.execute("""
            INSERT INTO users (
                user_id,
                subject_id,
                role,
                is_active,
                notes
            )
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO NOTHING
        """, (
            user_id,
            user_id,
            "operator",
            True,
            "Auto-created during CSV upload"
        ))

        for r in rows:

            c.execute("""
                INSERT INTO csv_data (
                    session_id,
                    user_id,
                    timestamp,
                    pulse,
                    heart_rate,
                    spo2,
                    source,
                    filename,
                    raw_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                session_id,
                user_id,
                str(r.get("timestamp")) if r.get("timestamp") else None,
                r.get("pulse"),
                r.get("heart_rate") or r.get("pulse"),
                r.get("spo2"),
                r.get("source", "csv"),
                filename,
                json.dumps(r, default=str),
            ))

        con.commit()

        c.close()
        con.close()

        return jsonify({
            "status": "csv_saved",
            "records": len(rows),
            "session_id": session_id,
            "user_id": user_id,
            "file": filename,
        })

    except Exception as e:

        traceback.print_exc()

        if con:
            con.rollback()
            con.close()

        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

    finally:

        if os.path.exists(temp_path):
            os.remove(temp_path)


# =========================================================
# RAW DATA API
# =========================================================

@research_bp.route("/api/fit_data")
@login_required
@role_required("viewer", "operator", "researcher", "admin")
@limiter.limit(PERF_LIMIT)
def fit_data():

    session_id = request.args.get("session_id")

    con = None

    try:

        con = db()
        c = con.cursor()

        c.execute("""
            SELECT timestamp, heart_rate, pulse, hr, spo2, rr_interval, hrv
            FROM fit_data
            WHERE session_id=%s
            ORDER BY id ASC
        """, (
            session_id,
        ))

        rows = c.fetchall()

        c.close()
        con.close()

        return jsonify([
            {
                "timestamp": r[0],
                "heart_rate": r[1] or r[2] or r[3],
                "pulse": r[2] or r[1] or r[3],
                "hr": r[3] or r[1] or r[2],
                "spo2": r[4],
                "rr_interval": r[5],
                "rr": r[5],
                "hrv": r[6],
            }
            for r in rows
        ])

    except Exception as e:

        traceback.print_exc()

        if con:
            con.close()

        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500


@research_bp.route("/api/csv_data")
@login_required
@role_required("viewer", "operator", "researcher", "admin")
@limiter.limit(PERF_LIMIT)
def csv_data():

    session_id = request.args.get("session_id")

    con = None

    try:

        con = db()
        c = con.cursor()

        c.execute("""
            SELECT timestamp, pulse, heart_rate, spo2
            FROM csv_data
            WHERE session_id=%s
            ORDER BY id ASC
        """, (
            session_id,
        ))

        rows = c.fetchall()

        c.close()
        con.close()

        return jsonify([
            {
                "timestamp": r[0],
                "pulse": r[1] or r[2],
                "heart_rate": r[2] or r[1],
                "spo2": r[3],
            }
            for r in rows
        ])

    except Exception as e:

        traceback.print_exc()

        if con:
            con.close()

        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500


@research_bp.route("/api/fit_timeseries/<session_id>")
@login_required
@role_required("viewer", "operator", "researcher", "admin")
@limiter.limit(PERF_LIMIT)
def fit_timeseries(session_id):

    con = None

    try:

        con = db()
        c = con.cursor()

        c.execute("""
            SELECT timestamp, pulse, heart_rate, spo2, hrv
            FROM fit_data
            WHERE session_id=%s
            ORDER BY id ASC
        """, (
            session_id,
        ))

        rows = c.fetchall()

        c.close()
        con.close()

        data = {
            "time": [],
            "pulse": [],
            "spo2": [],
            "hrv": [],
            "status": [],
        }

        for r in rows:

            pulse = r[1] or r[2]
            spo2 = r[3]
            hrv = r[4]

            if spo2 is not None and spo2 < 90:
                status = "hypoxia"

            elif hrv is not None and hrv < 30:
                status = "stress"

            else:
                status = "good"

            data["time"].append(r[0])
            data["pulse"].append(pulse)
            data["spo2"].append(spo2)
            data["hrv"].append(hrv)
            data["status"].append(status)

        return jsonify(data)

    except Exception as e:

        traceback.print_exc()

        if con:
            con.close()

        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500


# =========================================================
# SAVE PHASES
# =========================================================

@csrf.exempt
@research_bp.route("/api/save_phase", methods=["POST"])
@login_required
@role_required("admin", "researcher", "operator")
@limiter.limit("120 per minute")
def save_phase():

    con = None

    try:

        data = request.json or {}

        con = db()
        c = con.cursor()

        c.execute("""
            INSERT INTO users (
                user_id,
                subject_id,
                role,
                is_active,
                notes
            )
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO NOTHING
        """, (
            data.get("user_id"),
            data.get("user_id"),
            "operator",
            True,
            "Auto-created during phase save"
        ))

        phase = data.get("phase")

        c.execute("""
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
                source,
                timestamp
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
        """, (
            data.get("session_id"),
            data.get("user_id"),
            phase,
            "garmin" if phase == "during" else "pulseox",
            "COMPLETED",
            data.get("spo2"),
            data.get("pulse"),
            data.get("hrv"),
            data.get("pressure_kpa"),
            data.get("pressure_ata"),
            data.get("pressure_ata"),
            data.get("oxygen_flow_lpm"),
            data.get("oxygen_mask_percent"),
            data.get("chamber_temperature"),
            data.get("body_temperature"),
            data.get("humidity"),
            json.dumps(data, default=str),
            "manual_phase",
        ))

        con.commit()

        c.close()
        con.close()

        return jsonify({
            "status": "saved"
        })

    except Exception as e:

        traceback.print_exc()

        if con:
            con.rollback()
            con.close()

        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500


# =========================================================
# SAVE FULL SESSION — RAW + FEATURE PACKAGE
# =========================================================

@csrf.exempt
@research_bp.route("/api/save_full_session", methods=["POST"])
@login_required
@role_required("admin", "researcher", "operator")
@limiter.limit("60 per minute")
def save_full_session():

    con = None

    try:

        data = request.get_json() or {}

        if not data:
            return jsonify({"error": "no data"}), 400

        session_id = data.get("session_id")
        user_id = data.get("user_id")

        if not session_id:
            return jsonify({"error": "missing session_id"}), 400

        if not user_id:
            return jsonify({"error": "missing user_id"}), 400

        con = db()
        c = con.cursor()

        c.execute("""
            INSERT INTO users (
                user_id,
                subject_id,
                role,
                is_active,
                notes
            )
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO NOTHING
        """, (
            user_id,
            user_id,
            "operator",
            True,
            "Auto-created during full session save"
        ))

        c.execute("""
            SELECT timestamp, pulse, heart_rate, spo2, hrv, rr_interval
            FROM fit_data
            WHERE session_id=%s
            ORDER BY id ASC
        """, (
            session_id,
        ))

        fit_rows = c.fetchall()

        print("FIT DB ROWS:", len(fit_rows))

        c.execute("""
            SELECT timestamp, pulse, heart_rate, spo2
            FROM csv_data
            WHERE session_id=%s
            ORDER BY id ASC
        """, (
            session_id,
        ))

        csv_rows = c.fetchall()

        print("CSV DB ROWS:", len(csv_rows))

        fit_timeline = []

        for r in fit_rows:

            fit_timeline.append({
                "timestamp": r[0],
                "pulse": r[1] or r[2],
                "heart_rate": r[2] or r[1],
                "spo2": r[3],
                "hrv": r[4],
                "rr_interval": r[5],
                "source": "fit",
            })

        csv_timeline = []

        for r in csv_rows:

            csv_timeline.append({
                "timestamp": r[0],
                "pulse": r[1] or r[2],
                "heart_rate": r[2] or r[1],
                "spo2": r[3],
                "source": "csv",
            })

        csv_pulse_clean = [
            x.get("pulse")
            for x in csv_timeline
            if x.get("pulse") is not None and x.get("pulse") >= 30
        ]

        csv_spo2_clean = [
            x.get("spo2")
            for x in csv_timeline
            if x.get("spo2") is not None
        ]

        fit_pulse_clean = [
            x.get("pulse")
            for x in fit_timeline
            if x.get("pulse") is not None and x.get("pulse") >= 30
        ]

        fit_hrv_clean = [
            x.get("hrv")
            for x in fit_timeline
            if x.get("hrv") is not None
        ]

        feature_package = {
            "fit_samples": len(fit_timeline),
            "csv_samples": len(csv_timeline),

            "avg_fit_hr": avg(fit_pulse_clean),
            "min_fit_hr": min(fit_pulse_clean, default=None),
            "max_fit_hr": max(fit_pulse_clean, default=None),

            "avg_csv_pulse": avg(csv_pulse_clean),
            "min_csv_pulse": min(csv_pulse_clean, default=None),
            "max_csv_pulse": max(csv_pulse_clean, default=None),

            "avg_csv_spo2": avg(csv_spo2_clean),
            "min_spo2": min(csv_spo2_clean, default=None),
            "max_spo2": max(csv_spo2_clean, default=None),

            "avg_hrv": avg(fit_hrv_clean),

            "csv_pulse_artifacts": len([
                x for x in csv_timeline
                if x.get("pulse") is not None and x.get("pulse") < 30
            ]),
        }

        during_payload = {
            "phase_data": data.get("during", {}),
            "fit_timeline": fit_timeline,
            "csv_timeline": csv_timeline,
            "merged_timeline": data.get("during", {}).get("merged", []),
            "features": feature_package,
        }

        c.execute("""
            INSERT INTO full_sessions (
                session_id,
                user_id,
                session_status,
                pre_json,
                during_json,
                post_json,
                summary,
                completed,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, 1, CURRENT_TIMESTAMP)

            ON CONFLICT (session_id)
            DO UPDATE SET
                user_id = EXCLUDED.user_id,
                session_status = EXCLUDED.session_status,
                pre_json = EXCLUDED.pre_json,
                during_json = EXCLUDED.during_json,
                post_json = EXCLUDED.post_json,
                summary = EXCLUDED.summary,
                completed = EXCLUDED.completed
        """, (
            session_id,
            user_id,
            "completed",
            json.dumps(data.get("pre", {}), default=str),
            json.dumps(during_payload, default=str),
            json.dumps(data.get("post", {}), default=str),
            json.dumps(feature_package, default=str),
        ))

        con.commit()

        c.execute("""
            SELECT COUNT(*)
            FROM full_sessions
            WHERE session_id=%s
        """, (
            session_id,
        ))

        saved_count = c.fetchone()[0]

        print("FULL SESSION SAVED:", session_id)
        print("FULL SESSION COUNT:", saved_count)

        c.close()
        con.close()

        if saved_count == 0:
            return jsonify({
                "error": "full session was not saved"
            }), 500

        return jsonify({
            "status": "ok",
            "session_id": session_id,
            "user_id": user_id,
            "saved_count": saved_count,
            "features": feature_package,
        })

    except Exception as e:

        traceback.print_exc()

        if con:
            con.rollback()
            con.close()

        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500


# =========================================================
# SESSIONS API
# =========================================================

@research_bp.route("/api/sessions")
@login_required
@limiter.limit(PERF_LIMIT)
def sessions():

    con = None

    try:

        con = db()
        c = con.cursor()

        if current_user.role in ["admin", "researcher"]:

            c.execute("""
                SELECT
                    session_id,
                    COALESCE(user_id, 'UNKNOWN') as user_id,
                    completed,
                    created_at
                FROM full_sessions
                ORDER BY created_at DESC
            """)

        else:

            c.execute("""
                SELECT
                    session_id,
                    COALESCE(user_id, 'UNKNOWN') as user_id,
                    completed,
                    created_at
                FROM full_sessions
                WHERE user_id=%s
                ORDER BY created_at DESC
            """, (
                current_user.user_id,
            ))

        rows = c.fetchall()

        data = []

        for r in rows:

            data.append({
                "session_id": r[0],
                "user_id": r[1],
                "completed": bool(r[2]),
                "date": r[3].isoformat() if r[3] else None,
            })

        c.close()
        con.close()

        return jsonify({
            "status": "ok",
            "count": len(data),
            "sessions": data
        })

    except Exception as e:

        traceback.print_exc()

        if con:
            con.close()

        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500


# =========================================================
# DELETE SESSIONS
# =========================================================

@csrf.exempt
@research_bp.route("/api/delete_sessions", methods=["POST"])
@login_required
@role_required("admin")
@limiter.limit("30 per minute")
def delete_sessions():

    con = None

    try:

        data = request.get_json() or {}

        sessions = data.get("sessions", [])

        if not sessions:
            return jsonify({
                "error": "missing sessions"
            }), 400

        con = db()
        c = con.cursor()

        for session_id in sessions:

            c.execute("""
                DELETE FROM fit_data
                WHERE session_id=%s
            """, (
                session_id,
            ))

            c.execute("""
                DELETE FROM csv_data
                WHERE session_id=%s
            """, (
                session_id,
            ))

            c.execute("""
                DELETE FROM tests
                WHERE session_id=%s
            """, (
                session_id,
            ))

            c.execute("""
                DELETE FROM full_sessions
                WHERE session_id=%s
            """, (
                session_id,
            ))

        con.commit()

        c.close()
        con.close()

        return jsonify({
            "status": "deleted",
            "deleted": sessions
        })

    except Exception as e:

        traceback.print_exc()

        if con:
            con.rollback()
            con.close()

        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500


# =========================================================
# MERGE TIMELINE
# =========================================================

@csrf.exempt
@research_bp.route("/api/during_merge", methods=["POST"])
@login_required
@role_required("operator", "researcher", "admin")
@limiter.limit("120 per minute")
def during_merge():

    try:
        data = request.get_json() or {}
        session_id = data.get("session_id")

        if not session_id:
            return jsonify({"error": "missing session_id"}), 400

        con = db()
        c = con.cursor()

        c.execute("""
            SELECT timestamp, heart_rate, pulse, hr, rr_interval, hrv, spo2
            FROM fit_data
            WHERE session_id=%s
            ORDER BY id ASC
        """, (session_id,))
        fit_rows = c.fetchall()

        c.execute("""
            SELECT timestamp, pulse, heart_rate, spo2
            FROM csv_data
            WHERE session_id=%s
            ORDER BY id ASC
        """, (session_id,))
        csv_rows = c.fetchall()

        con.close()

        fit = []

        for r in fit_rows:
            fit.append({
                "timestamp": r[0],
                "heart_rate": r[1] or r[2] or r[3],
                "hr": r[3] or r[1] or r[2],
                "pulse": r[2] or r[1] or r[3],
                "rr_interval": r[4],
                "hrv": r[5],
                "spo2": r[6],
                "source": "fit",
            })

        csv = []

        for r in csv_rows:
            csv.append({
                "timestamp": r[0],
                "pulse": r[1] or r[2],
                "heart_rate": r[2] or r[1],
                "spo2": r[3],
                "source": "csv",
            })

        if not fit and not csv:
            return jsonify({"error": "no fit or csv data"}), 404

        if fit and not csv:
            return jsonify({
                "status": "ok",
                "mode": "fit_only",
                "fit_samples": len(fit),
                "csv_samples": 0,
                "merged_samples": len(fit),
                "merged": fit,
            })

        if csv and not fit:
            return jsonify({
                "status": "ok",
                "mode": "csv_only",
                "fit_samples": 0,
                "csv_samples": len(csv),
                "merged_samples": len(csv),
                "merged": csv,
            })

        csv_by_time = {
            str(row["timestamp"]): row
            for row in csv
        }

        merged = []

        for f in fit:
            t = str(f.get("timestamp"))
            c_row = csv_by_time.get(t)

            row = {
                "timestamp": f.get("timestamp"),
                "heart_rate": f.get("heart_rate"),
                "hr": f.get("hr"),
                "pulse": f.get("pulse"),
                "rr_interval": f.get("rr_interval"),
                "hrv": f.get("hrv"),
                "spo2": f.get("spo2"),
                "source": "merged",
            }

            if c_row:
                row["pulse"] = c_row.get("pulse") or row.get("pulse")
                row["spo2"] = c_row.get("spo2") or row.get("spo2")

            merged.append(row)

        return jsonify({
            "status": "ok",
            "mode": "fit_csv",
            "fit_samples": len(fit),
            "csv_samples": len(csv),
            "merged_samples": len(merged),
            "merged": merged,
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500


# =========================================================
# AI ANALYSIS
# =========================================================

@csrf.exempt
@research_bp.route("/api/run_analysis", methods=["POST"])
@login_required
@role_required("operator", "researcher", "admin")
@limiter.limit("60 per hour")
def run_analysis():

    con = None

    try:
        data = request.get_json() or {}
        session_id = data.get("session_id")

        if not session_id:
            return jsonify({"error": "missing session_id"}), 400

        con = db()
        c = con.cursor()

        c.execute("""
            SELECT pre_json, during_json, post_json, summary
            FROM full_sessions
            WHERE session_id=%s
        """, (session_id,))

        row = c.fetchone()

        c.close()
        con.close()

        if not row:
            return jsonify({"error": "no full session data"}), 404

        pre = json.loads(row[0]) if row[0] else {}
        during = json.loads(row[1]) if row[1] else {}
        post = json.loads(row[2]) if row[2] else {}
        features = json.loads(row[3]) if row[3] else {}

        fit_timeline = during.get("fit_timeline", [])
        csv_timeline = during.get("csv_timeline", [])
        merged_timeline = during.get("merged_timeline", [])

        timeline = merged_timeline or csv_timeline or fit_timeline or []

        result = calculate_session_score(pre, post, features)

        return jsonify({
            "status": "ok",
            "session_id": session_id,
            "summary": result["summary"],
            "score": result["score"],
            "risk_level": result["risk_level"],
            "anomaly": result["anomaly"],
            "reasons": result["reasons"],
            "positive_findings": result["positive_findings"],
            "score_type": "AI Research Risk Score",
            "medical_disclaimer": "Research-only score. Not a medical diagnosis.",
            "features": features,
            "timeline": timeline,
            "pre": pre,
            "during": during,
            "post": post,
        })

    except Exception as e:
        traceback.print_exc()

        if con:
            con.close()

        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

# =========================================================
# AI LATEST
# =========================================================

@research_bp.route("/api/ai_latest")
@login_required
@role_required("viewer", "operator", "researcher", "admin")
@limiter.limit("60 per minute")
def ai_latest():

    con = None

    try:
        con = db()
        c = con.cursor()

        c.execute("""
            SELECT
                session_id,
                pre_json,
                post_json,
                summary
            FROM full_sessions
            WHERE completed=1
            ORDER BY id DESC
            LIMIT 1
        """)

        row = c.fetchone()

        c.close()
        con.close()

        if not row:
            return jsonify({"error": "no data"}), 404

        session_id = row[0]
        pre = json.loads(row[1]) if row[1] else {}
        post = json.loads(row[2]) if row[2] else {}
        features = json.loads(row[3]) if row[3] else {}

        result = calculate_session_score(pre, post, features)

        return jsonify({
            "status": "ok",
            "session_id": session_id,
            "score": result["score"],
            "risk_level": result["risk_level"],
            "anomaly": result["anomaly"],
            "summary": result["summary"],
            "reasons": result["reasons"],
            "positive_findings": result["positive_findings"],
            "score_type": "AI Research Risk Score",
            "medical_disclaimer": "Research-only score. Not a medical diagnosis.",
            "features": features,
        })

    except Exception as e:
        traceback.print_exc()

        if con:
            con.close()

        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500


# =========================================================
# USER TRENDS
# =========================================================

@research_bp.route("/api/user_trends/<user_id>")
@login_required
@role_required("viewer", "operator", "researcher", "admin")
@limiter.limit("120 per minute")
def user_trends(user_id):

    con = None

    try:

        con = db()
        c = con.cursor()

        c.execute("""
            SELECT
                session_id,
                summary,
                created_at
            FROM full_sessions
            WHERE user_id=%s
            ORDER BY created_at ASC
        """, (
            user_id,
        ))

        rows = c.fetchall()

        c.close()
        con.close()

        timeline = []

        for r in rows:

            summary = json.loads(r[1]) if r[1] else {}

            timeline.append({
                "session_id": r[0],
                "score": summary.get("score"),
                "risk_level": summary.get("risk_level"),
                "created_at": r[2].isoformat() if r[2] else None,
            })

        return jsonify({
            "status": "ok",
            "user_id": user_id,
            "records": len(timeline),
            "timeline": timeline,
        })

    except Exception as e:

        traceback.print_exc()

        if con:
            con.close()

        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500


# =========================================================
# PLAYWRIGHT QA
# =========================================================

@csrf.exempt
@research_bp.route("/api/run_playwright", methods=["POST"])
@login_required
@role_required("admin")
@limiter.limit("10 per hour")
def run_playwright():

    import subprocess

    try:

        result = subprocess.run(
            ["npm", "run", "test:e2e:list"],
            cwd=os.getcwd(),
            capture_output=True,
            text=True,
            env={
        **os.environ,
        "PLAYWRIGHT_BASE_URL": os.getenv(
            "PLAYWRIGHT_BASE_URL",
            "http://127.0.0.1:5000"
        )
            }
        )

        return jsonify({
            "status": "success" if result.returncode == 0 else "error",
            "returncode": result.returncode,
            "stdout": result.stdout[-12000:],
            "stderr": result.stderr[-5000:],
            "command": "npm run test:e2e:list",
            "report_path": "/admin/playwright-report/index.html"
        })

    except Exception as e:

        traceback.print_exc()

        return jsonify({
            "status": "error",
            "returncode": None,
            "error": str(e),
            "command": "npm run test:e2e:list"
        }), 500

# =========================================================
# AI TEST GENERATOR
# =========================================================

@csrf.exempt
@research_bp.route("/api/generate_test", methods=["POST"])
@login_required
@role_required("researcher", "admin")
@limiter.limit("30 per hour")
def generate_test():

    data = request.get_json(silent=True) or {}

    prompt = data.get("prompt", "")
    session_id = data.get("session_id")
    user_id = data.get("user_id")
    target = data.get("target", "hbot_ai_pipeline")

    generated = generate_playwright_test(
        prompt=prompt,
        session_id=session_id,
        user_id=user_id,
        target=target,
    )

    return jsonify({
        "status": "generated",
        "session_id": session_id,
        "user_id": user_id,
        "target": target,
        "prompt": prompt,
        "test": generated,
    })


# =========================================================
# DEBUG DB
# =========================================================

@research_bp.route("/debug/db")
@login_required
@role_required("admin")
@limiter.limit("30 per minute")
def debug_db():

    con = None

    try:

        con = db()
        c = con.cursor()

        result = {}

        for table in [
            "tests",
            "fit_data",
            "csv_data",
            "full_sessions",
            "users"
        ]:

            c.execute(
                f"SELECT COUNT(*) FROM {table}"
            )

            result[table] = c.fetchone()[0]

        c.close()
        con.close()

        return jsonify({
            "status": "ok",
            "database": result
        })

    except Exception as e:

        traceback.print_exc()

        if con:
            con.close()

        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

# =========================================================
# ADMIN PLAYWRIGHT REPORT
# =========================================================

@research_bp.route("/admin/playwright-report/<path:filename>")
@login_required
@role_required("admin")
def playwright_report(filename):

    report_dir = os.path.join(
        os.getcwd(),
        "playwright-report"
    )

    return send_from_directory(
        report_dir,
        filename
    ) 
    
# =========================================================
# GATLING HTML REPORT
# =========================================================

@research_bp.route(
    "/admin/gatling-report/<path:filename>"
)
@login_required
@role_required("admin")
def gatling_report(filename):

    report_dir = Path(
        "tests/performance/gatling/target/gatling"
    )

    return send_from_directory(
        report_dir,
        filename
    )