from flask import Blueprint, render_template, jsonify, request, send_file, session
from database import db

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

import os
import uuid
import json
import sqlite3
import datetime
import traceback


research_bp = Blueprint("research", __name__)


# =========================================================
# HELPERS
# =========================================================

def avg(values):
    clean = [v for v in values if v is not None]
    return round(sum(clean) / len(clean), 2) if clean else None


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
            reasons.append("DURING SpO2 dropped below 90% - high warning")
        elif features["min_spo2"] < 92:
            score -= 30
            reasons.append("DURING SpO2 dropped to 90-91% - warning")
        elif features["min_spo2"] < 94:
            score -= 15
            reasons.append("DURING SpO2 is borderline low")

    # POST SpO2
    if post_spo2 is not None:
        if post_spo2 < 90:
            score -= 40
            reasons.append("POST SpO2 below 90% - high warning")
        elif post_spo2 < 92:
            score -= 30
            reasons.append("POST SpO2 90-91% - warning")
        elif post_spo2 < 94:
            score -= 15
            reasons.append("POST SpO2 92-93% - borderline")

    # PRE -> POST SpO2 drop
    if pre_spo2 is not None and post_spo2 is not None:
        spo2_drop = pre_spo2 - post_spo2

        if spo2_drop >= 5:
            score -= 25
            reasons.append(f"SpO2 dropped by {spo2_drop}% from PRE to POST")
        elif spo2_drop >= 3:
            score -= 10
            reasons.append(f"SpO2 dropped by {spo2_drop}% from PRE to POST")

    # HRV
    if features.get("avg_hrv") is not None and features["avg_hrv"] < 30:
        score -= 20
        reasons.append("Average HRV is below 30 ms")

    # FIT HR
    if features.get("max_fit_hr") is not None and features["max_fit_hr"] > 160:
        score -= 15
        reasons.append("FIT HR exceeded 160 bpm")

    # CSV Pulse
    if features.get("max_csv_pulse") is not None and features["max_csv_pulse"] > 160:
        score -= 15
        reasons.append("CSV pulse exceeded 160 bpm")

    # POST Pulse
    if post_pulse is not None and post_pulse > 120:
        score -= 10
        reasons.append("POST pulse is elevated above 120 bpm")

    # Positive findings
    if features.get("avg_csv_spo2") is not None:
        if features["avg_csv_spo2"] >= 97:
            positive_findings.append("Excellent oxygen saturation during session")
        elif features["avg_csv_spo2"] >= 95:
            positive_findings.append("Normal oxygen saturation maintained")

    if post_spo2 is not None:
        if post_spo2 >= 95:
            positive_findings.append("Post-session SpO2 recovered to normal range")
        elif post_spo2 >= 92:
            positive_findings.append("Post-session SpO2 acceptable")

    if features.get("max_fit_hr") is not None and features["max_fit_hr"] < 140:
        positive_findings.append("Heart rate response remained stable")

    if features.get("avg_hrv") is not None and features["avg_hrv"] >= 40:
        positive_findings.append("HRV indicates good autonomic recovery")

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


def ensure_tables():
    con = db()
    c = con.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS fit_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            user_id TEXT,
            timestamp TEXT,
            heart_rate REAL,
            pulse REAL,
            hr REAL,
            spo2 REAL,
            rr_interval REAL,
            hrv REAL,
            source TEXT,
            raw_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS csv_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            user_id TEXT,
            timestamp TEXT,
            pulse REAL,
            heart_rate REAL,
            spo2 REAL,
            source TEXT,
            raw_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    con.commit()
    con.close()


# =========================================================
# PAGES
# =========================================================

@research_bp.route("/platform")
def research_platform():
    return render_template("research_platform.html")


@research_bp.route("/research")
def research_dashboard():
    return render_template("research_dashboard.html")

@research_bp.route("/admin")
def admin_panel():
    return render_template("admin_panel.html")


@research_bp.route("/chamber")
def chamber_testing():
    ensure_tables()
    return render_template("chamber_testing.html")

@research_bp.route("/performance-tests")
def performance_tests():
    return render_template("performance_tests.html")  


# =========================================================
# USERS
# =========================================================

@research_bp.route("/api/users", methods=["GET", "POST"])
def users():
    con = db()
    con.row_factory = sqlite3.Row
    c = con.cursor()

    if request.method == "GET":
        rows = c.execute("SELECT * FROM users ORDER BY id DESC").fetchall()
        con.close()

        return jsonify([
            {
                "user_id": r["user_id"] or str(r["id"]),
                "subject_id": r["subject_id"],
                "sex": r["sex"],
                "age": r["age"],
                "weight": r["weight"],
                "notes": r["notes"],
            }
            for r in rows
        ])

    data = request.get_json() or {}

    try:
        user_id = str(uuid.uuid4())[:8]

        c.execute("""
            INSERT INTO users(user_id, subject_id, sex, age, weight, notes)
            VALUES(?,?,?,?,?,?)
        """, (
            user_id,
            data.get("subject_id"),
            data.get("sex"),
            data.get("age"),
            data.get("weight"),
            data.get("notes"),
        ))

        con.commit()
        return jsonify({"status": "ok", "user_id": user_id})

    except sqlite3.IntegrityError:
        return jsonify({"error": "User already exists"}), 400

    finally:
        con.close()


@research_bp.route("/api/delete_user", methods=["POST"])
def delete_user():
    user_id = request.json.get("user_id")

    con = db()
    c = con.cursor()

    c.execute("DELETE FROM users WHERE user_id=? OR id=?", (user_id, user_id))

    con.commit()
    con.close()

    return jsonify({"status": "ok"})


# =========================================================
# UPLOAD FIT / CSV RAW
# =========================================================

@research_bp.route("/upload_fit", methods=["POST"])
def upload_fit():
    ensure_tables()

    file = request.files.get("file")
    session_id = request.form.get("session_id")

    if not file or not session_id:
        return jsonify({"error": "missing file or session_id"}), 400

    user_id = session_id.split("_")[0] if "_" in session_id else None
    filename = file.filename.lower()

    if not filename.endswith(".fit"):
        return jsonify({"error": "unsupported FIT format"}), 400

    os.makedirs("data/uploads/temp", exist_ok=True)
    temp_path = f"data/uploads/temp/{uuid.uuid4()}_{filename}"

    file.save(temp_path)

    try:
        rows = parse_fit_file(temp_path)

        con = db()
        c = con.cursor()

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
                    raw_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                json.dumps(r, default=str),
            ))

        con.commit()
        con.close()

        return jsonify({
            "status": "fit_saved",
            "records": len(rows),
            "session_id": session_id,
            "user_id": user_id,
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@research_bp.route("/upload_csv", methods=["POST"])
def upload_csv():
    ensure_tables()

    file = request.files.get("file")
    session_id = request.form.get("session_id")

    if not file or not session_id:
        return jsonify({"error": "missing file or session_id"}), 400

    user_id = session_id.split("_")[0] if "_" in session_id else None
    filename = file.filename.lower()

    if not filename.endswith(".csv"):
        return jsonify({"error": "unsupported CSV format"}), 400

    os.makedirs("data/uploads/temp", exist_ok=True)
    temp_path = f"data/uploads/temp/{uuid.uuid4()}_{filename}"

    file.save(temp_path)

    try:
        rows = parse_csv_file(temp_path)

        con = db()
        c = con.cursor()

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
                    raw_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session_id,
                user_id,
                str(r.get("timestamp")) if r.get("timestamp") else None,
                r.get("pulse"),
                r.get("heart_rate") or r.get("pulse"),
                r.get("spo2"),
                r.get("source", "csv"),
                json.dumps(r, default=str),
            ))

        con.commit()
        con.close()

        return jsonify({
            "status": "csv_saved",
            "records": len(rows),
            "session_id": session_id,
            "user_id": user_id,
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


# =========================================================
# RAW DATA API
# =========================================================

@research_bp.route("/api/fit_data")
def fit_data():
    ensure_tables()

    session_id = request.args.get("session_id")

    con = db()
    c = con.cursor()

    c.execute("""
        SELECT timestamp, heart_rate, pulse, hr, spo2, rr_interval, hrv
        FROM fit_data
        WHERE session_id=?
        ORDER BY id ASC
    """, (session_id,))

    rows = c.fetchall()
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


@research_bp.route("/api/csv_data")
def csv_data():
    ensure_tables()

    session_id = request.args.get("session_id")

    con = db()
    c = con.cursor()

    c.execute("""
        SELECT timestamp, pulse, heart_rate, spo2
        FROM csv_data
        WHERE session_id=?
        ORDER BY id ASC
    """, (session_id,))

    rows = c.fetchall()
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


@research_bp.route("/api/fit_timeseries/<session_id>")
def fit_timeseries(session_id):
    ensure_tables()

    con = db()
    c = con.cursor()

    c.execute("""
        SELECT timestamp, pulse, heart_rate, spo2, hrv
        FROM fit_data
        WHERE session_id=?
        ORDER BY id ASC
    """, (session_id,))

    rows = c.fetchall()
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


# =========================================================
# SAVE PHASES
# =========================================================

@research_bp.route("/api/save_phase", methods=["POST"])
def save_phase():
    data = request.json or {}

    con = db()
    c = con.cursor()

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
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
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
    con.close()

    return jsonify({"status": "saved"})


# =========================================================
# SAVE FULL SESSION — RAW + FEATURE PACKAGE
# =========================================================

@research_bp.route("/api/save_full_session", methods=["POST"])
def save_full_session():
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
        SELECT timestamp, pulse, heart_rate, spo2, hrv, rr_interval
        FROM fit_data
        WHERE session_id=?
        ORDER BY id ASC
    """, (session_id,))

    fit_rows = c.fetchall()

    c.execute("""
        SELECT timestamp, pulse, heart_rate, spo2
        FROM csv_data
        WHERE session_id=?
        ORDER BY id ASC
    """, (session_id,))

    csv_rows = c.fetchall()

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
        INSERT OR REPLACE INTO full_sessions (
            session_id,
            user_id,
            pre_json,
            during_json,
            post_json,
            summary,
            completed,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, 1, datetime('now'))
    """, (
        session_id,
        user_id,
        json.dumps(data.get("pre", {}), default=str),
        json.dumps(during_payload, default=str),
        json.dumps(data.get("post", {}), default=str),
        json.dumps(feature_package, default=str),
    ))

    con.commit()

    c.execute("""
        SELECT COUNT(*)
        FROM full_sessions
        WHERE session_id=?
    """, (session_id,))

    saved_count = c.fetchone()[0]

    print("FULL SESSION SAVED:", session_id)
    print("FULL SESSION COUNT:", saved_count)

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


# =========================================================
# SESSIONS / ANALYSIS
# =========================================================

@research_bp.route("/api/sessions")
def sessions():
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
    con.close()

    data = []

    for r in rows:
        data.append({
            "session_id": r[0],
            "user_id": r[1],
            "completed": r[2],
            "date": r[3],
        })

    print("API SESSIONS:", data)

    return jsonify(data)


@research_bp.route("/api/delete_sessions", methods=["POST"])
def delete_sessions():
    data = request.json or {}
    session_ids = data.get("sessions", [])

    if not session_ids:
        return jsonify({"error": "no sessions"}), 400

    con = db()
    c = con.cursor()

    placeholders = ",".join(["?"] * len(session_ids))

    c.execute(f"DELETE FROM tests WHERE session_id IN ({placeholders})", session_ids)
    c.execute(f"DELETE FROM fit_data WHERE session_id IN ({placeholders})", session_ids)
    c.execute(f"DELETE FROM csv_data WHERE session_id IN ({placeholders})", session_ids)
    c.execute(f"DELETE FROM full_sessions WHERE session_id IN ({placeholders})", session_ids)

    con.commit()
    con.close()

    return jsonify({"status": "deleted", "count": len(session_ids)})


@research_bp.route("/api/run_analysis", methods=["POST"])
def run_analysis():
    data = request.get_json() or {}
    session_id = data.get("session_id")

    if not session_id:
        return jsonify({"error": "missing session_id"}), 400

    con = db()
    c = con.cursor()

    c.execute("""
        SELECT pre_json, during_json, post_json, summary
        FROM full_sessions
        WHERE session_id=?
    """, (session_id,))

    row = c.fetchone()
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


@research_bp.route("/api/user_trends/<user_id>")
def user_trends(user_id):
    con = db()
    c = con.cursor()

    c.execute("""
        SELECT
            session_id,
            pre_json,
            during_json,
            post_json,
            summary,
            created_at
        FROM full_sessions
        WHERE user_id=?
        AND completed=1
        ORDER BY created_at ASC
    """, (user_id,))

    rows = c.fetchall()
    con.close()

    if not rows:
        return jsonify({
            "error": "no sessions for user",
            "user_id": user_id,
        }), 404

    sessions = []

    for r in rows:
        session_id = r[0]
        pre = json.loads(r[1]) if r[1] else {}
        during = json.loads(r[2]) if r[2] else {}
        post = json.loads(r[3]) if r[3] else {}
        features = json.loads(r[4]) if r[4] else {}
        created_at = r[5]

        result = calculate_session_score(pre, post, features)

        pre_spo2 = pre.get("spo2")
        post_spo2 = post.get("spo2")
        pre_pulse = pre.get("pulse")
        post_pulse = post.get("pulse")

        spo2_delta = None
        pulse_delta = None

        if pre_spo2 is not None and post_spo2 is not None:
            spo2_delta = post_spo2 - pre_spo2

        if pre_pulse is not None and post_pulse is not None:
            pulse_delta = post_pulse - pre_pulse

        sessions.append({
            "session_id": session_id,
            "created_at": created_at,

            "score": result["score"],
            "risk_level": result["risk_level"],
            "anomaly": result["anomaly"],
            "reasons": result["reasons"],
            "positive_findings": result["positive_findings"],
            "summary": result["summary"],

            "pre_spo2": pre_spo2,
            "post_spo2": post_spo2,
            "spo2_delta": spo2_delta,

            "pre_pulse": pre_pulse,
            "post_pulse": post_pulse,
            "pulse_delta": pulse_delta,

            "avg_csv_spo2": features.get("avg_csv_spo2"),
            "min_spo2": features.get("min_spo2"),
            "max_spo2": features.get("max_spo2"),

            "avg_csv_pulse": features.get("avg_csv_pulse"),
            "max_csv_pulse": features.get("max_csv_pulse"),

            "avg_fit_hr": features.get("avg_fit_hr"),
            "max_fit_hr": features.get("max_fit_hr"),

            "avg_hrv": features.get("avg_hrv"),
            "fit_samples": features.get("fit_samples"),
            "csv_samples": features.get("csv_samples"),
        })

    avg_score = avg([
        s["score"]
        for s in sessions
        if s.get("score") is not None
    ])

    avg_spo2_delta = avg([
        s["spo2_delta"]
        for s in sessions
        if s.get("spo2_delta") is not None
    ])

    avg_post_spo2 = avg([
        s["post_spo2"]
        for s in sessions
        if s.get("post_spo2") is not None
    ])

    anomaly_count = len([
        s for s in sessions
        if s.get("anomaly") is True
    ])

    trend_summary = "Stable trend"

    if anomaly_count > 0:
        trend_summary = "Some sessions require review"

    if avg_spo2_delta is not None and avg_spo2_delta <= -3:
        trend_summary = "Average PRE to POST SpO2 response is negative"

    if avg_score is not None and avg_score < 70:
        trend_summary = "Overall trend shows elevated risk"

    return jsonify({
        "status": "ok",
        "user_id": user_id,
        "session_count": len(sessions),
        "anomaly_count": anomaly_count,
        "avg_score": avg_score,
        "avg_post_spo2": avg_post_spo2,
        "avg_spo2_delta": avg_spo2_delta,
        "trend_summary": trend_summary,
        "score_type": "AI Research Trend Score",
        "medical_disclaimer": "Research-only trend. Not a medical diagnosis.",
        "sessions": sessions,
    })


@research_bp.route("/api/ai_latest")
def ai_latest():
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


# =========================================================
# OTHER
# =========================================================

@research_bp.route("/report")
def report():
    path = generate_report()
    return send_file(path, as_attachment=True)


@research_bp.route("/api/during_merge", methods=["POST"])
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
            WHERE session_id=?
            ORDER BY id ASC
        """, (session_id,))

        fit_rows = c.fetchall()

        c.execute("""
            SELECT timestamp, pulse, heart_rate, spo2
            FROM csv_data
            WHERE session_id=?
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
                "merged": fit,
            })

        if csv and not fit:
            return jsonify({
                "status": "ok",
                "mode": "csv_only",
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
        return jsonify({"error": str(e)}), 500


@research_bp.route("/api/run_playwright", methods=["POST"])
def run_playwright():

    import subprocess
    import os

    try:
        result = subprocess.run(
            ["npx.cmd", "playwright", "test"],
            cwd=os.getcwd(),
            capture_output=True,
            text=True
        )

        return jsonify({
            "status": "success" if result.returncode == 0 else "error",
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "command": "npx playwright test"
        })

    except Exception as e:
        traceback.print_exc()

        return jsonify({
            "status": "error",
            "returncode": None,
            "error": str(e),
            "command": "npx playwright test"
        }), 500


@research_bp.route("/api/generate_test", methods=["POST"])
def generate_test():

    data = request.json or {}

    prompt = data.get("prompt", "")
    session_id = data.get("session_id")
    user_id = data.get("user_id")
    target = data.get("target", "hbot_ai_pipeline")

    test_code = f"""
import {{ test, expect }} from '@playwright/test';

test('AI pipeline validates HBOT session analysis', async ({{ request }}) => {{

    const response = await request.post('/api/run_analysis', {{
        data: {{
            session_id: '{session_id}'
        }}
    }});

    expect(response.ok()).toBeTruthy();

    const body = await response.json();

    expect(body).toHaveProperty('status');
    expect(body).toHaveProperty('session_id');
    expect(body).toHaveProperty('score');
    expect(body).toHaveProperty('risk_level');
    expect(body).toHaveProperty('anomaly');
    expect(body).toHaveProperty('features');
    expect(body).toHaveProperty('timeline');

    expect(typeof body.score).toBe('number');
    expect(typeof body.anomaly).toBe('boolean');
    expect(Array.isArray(body.timeline)).toBeTruthy();
}});
"""

    return jsonify({
        "status": "generated",
        "session_id": session_id,
        "user_id": user_id,
        "target": target,
        "prompt": prompt,
        "test": test_code
    })


@research_bp.route("/debug/db")
def debug_db():
    con = db()
    c = con.cursor()

    result = {}

    for table in ["tests", "fit_data", "csv_data", "full_sessions"]:
        c.execute(f"SELECT COUNT(*) FROM {table}")
        result[table] = c.fetchone()[0]

    con.close()

    return jsonify(result)