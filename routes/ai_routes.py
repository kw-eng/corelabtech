# routes/ai_routes.py

from flask import (
    Blueprint,
    render_template,
    jsonify,
    request
)

from database_postgres import db

from ai.physiology_ai import analyze_physiology
from ai.anomaly_detection import detect_anomaly

from core.pipeline.pipeline_runner import run_full_pipeline

ai_bp = Blueprint("ai", __name__)


# =====================================================
# AI LAB PAGE
# =====================================================
@ai_bp.route("/ai_lab")
def ai_lab():

    con = db()
    c = con.cursor()

    c.execute("""
        SELECT
            id,
            session_id,
            timestamp,
            phase,
            spo2,
            pulse,
            hrv,
            pressure_ata
        FROM tests
        ORDER BY timestamp DESC
        LIMIT 100
    """)

    rows = c.fetchall()

    con.close()

    tests = []

    for r in rows:

        tests.append({
            "id": r[0],
            "session_id": r[1],
            "date": r[2],
            "phase": r[3],
            "spo2": r[4],
            "pulse": r[5],
            "hrv": r[6],
            "ata": r[7]
        })

    return render_template(
        "ai_lab.html",
        tests=tests
    )


# =====================================================
# AI ANALYSIS
# =====================================================
@ai_bp.route("/api/ai_lab_analysis", methods=["POST"])
def ai_lab_analysis():

    data = request.json or {}

    mode = data.get("mode", "selected")

    con = db()
    c = con.cursor()

    # =================================================
    # LATEST SESSION
    # =================================================
    if mode == "latest":

        c.execute("""
            SELECT
                spo2,
                pulse,
                hrv,
                pressure_ata
            FROM tests
            ORDER BY timestamp DESC
            LIMIT 20
        """)

        rows = c.fetchall()

    # =================================================
    # SELECTED IDS
    # =================================================
    else:

        ids = data.get("ids", [])

        if not ids:
            return jsonify({
                "error": "No selected IDs"
            }), 400

        placeholders = ",".join("?" for _ in ids)

        c.execute(f"""
            SELECT
                spo2,
                pulse,
                hrv,
                pressure_ata
            FROM tests
            WHERE id IN ({placeholders})
        """, ids)

        rows = c.fetchall()

    con.close()

    if not rows:
        return jsonify({
            "error": "No telemetry data"
        }), 404

    # =================================================
    # NORMALIZATION
    # =================================================
    spo2 = [r[0] for r in rows if r[0] is not None]
    pulse = [r[1] for r in rows if r[1] is not None]
    hrv = [r[2] for r in rows if r[2] is not None]
    ata = [r[3] for r in rows if r[3] is not None]

    avg_spo2 = round(sum(spo2) / len(spo2), 2) if spo2 else None
    avg_pulse = round(sum(pulse) / len(pulse), 2) if pulse else None
    avg_hrv = round(sum(hrv) / len(hrv), 2) if hrv else None
    avg_ata = round(sum(ata) / len(ata), 2) if ata else None

    # =================================================
    # AI SCORE
    # =================================================
    score = 50

    # SpO2
    if avg_spo2:

        if avg_spo2 >= 96:
            score += 20

        elif avg_spo2 < 90:
            score -= 20

    # HRV
    if avg_hrv:

        if avg_hrv >= 50:
            score += 20

        elif avg_hrv < 25:
            score -= 15

    # ATA
    if avg_ata:

        if avg_ata > 2.4:
            score -= 10

    # =================================================
    # ANOMALY
    # =================================================
    anomaly = detect_anomaly({
        "spo2": avg_spo2,
        "pulse": avg_pulse,
        "hrv": avg_hrv,
        "ata": avg_ata
    })

    # =================================================
    # AI SUMMARY
    # =================================================
    summary = analyze_physiology(
        spo2=avg_spo2,
        pulse=avg_pulse,
        hrv=avg_hrv,
        body_temp=None,
        chamber_temp=None
    )

    return jsonify({

        "score": score,
        "anomaly": anomaly,

        "summary": summary,

        "samples": len(rows),

        "avg_spo2": avg_spo2,
        "avg_pulse": avg_pulse,
        "avg_hrv": avg_hrv,
        "avg_ata": avg_ata,

        "mode": mode
    })


# =====================================================
# RUN FULL PIPELINE
# =====================================================
@ai_bp.route("/api/run_pipeline", methods=["POST"])
def run_pipeline():

    data = request.json or {}

    session_id = data.get("session_id")

    if not session_id:

        return jsonify({
            "error": "session_id required"
        }), 400

    result = run_full_pipeline(session_id)

    return jsonify(result)


# =====================================================
# LATEST AI
# =====================================================
@ai_bp.route("/api/ai_latest")
def ai_latest():

    con = db()
    c = con.cursor()

    c.execute("""
        SELECT
            spo2,
            pulse,
            hrv,
            pressure_ata
        FROM tests
        ORDER BY timestamp DESC
        LIMIT 20
    """)

    rows = c.fetchall()

    con.close()

    if not rows:

        return jsonify({
            "error": "No data"
        }), 404

    spo2 = [r[0] for r in rows if r[0] is not None]
    hrv = [r[2] for r in rows if r[2] is not None]

    score = 50

    if spo2 and min(spo2) > 94:
        score += 20

    if hrv and (sum(hrv) / len(hrv)) > 50:
        score += 20

    anomaly = False

    if spo2 and min(spo2) < 90:
        anomaly = True

    return jsonify({

        "score": score,
        "anomaly": anomaly,
        "summary": "Latest session analysis"

    })


# =====================================================
# PHYSIOLOGY DEMO
# =====================================================
@ai_bp.route("/ai/physiology")
def physiology_analysis():

    result = analyze_physiology(
        spo2=97,
        pulse=72,
        hrv=35,
        body_temp=36.8,
        chamber_temp=23
    )

    return jsonify(result)