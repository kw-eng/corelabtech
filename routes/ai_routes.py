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

    try:
        c.execute("""
            SELECT
                ai_result_id,
                session_id,
                overall_score,
                data_quality_score,
                anomaly_detected,
                summary,
                recommendations,
                features_json,
                result_json,
                created_at
            FROM ai_results
            WHERE session_id NOT LIKE 'PIPELINE_VALIDATION_%'
            ORDER BY created_at DESC, ai_result_id DESC
            LIMIT 1
        """)

        row = c.fetchone()

        if not row:
            return jsonify({
                "error": "No AI result"
            }), 404

        features = row[7] or {}
        result = row[8] or {}

        return jsonify({
            "status": "ok",
            "ai_result_id": row[0],
            "session_id": row[1],
            "score": row[2],
            "overall_score": row[2],
            "data_quality_score": row[3],
            "anomaly": bool(row[4]),
            "anomaly_detected": bool(row[4]),
            "summary": row[5],
            "recommendations": row[6],
            "features": features,
            "result": result,
            "product_mode": result.get("product_mode"),
            "wellness_status": result.get("wellness_status"),
            "session_flagged": result.get("session_flagged"),
            "elevated_load": result.get("elevated_load"),
            "oxygenation_drop": result.get("oxygenation_drop"),
            "sensor_alignment_warning": result.get("sensor_alignment_warning"),
            "quality_warnings": result.get("quality_warnings", []),
            "created_at": row[9].isoformat() if row[9] else None,
        })

    finally:
        c.close()
        con.close()


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
