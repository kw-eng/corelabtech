# routes/ai_qa_routes.py

import os
import subprocess
import traceback

from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from auth.decorators import role_required
from security.limiter import limiter
from security.csrf import csrf

# AI logic
from services.ai_engine import run_ai_analysis


ai_qa_bp = Blueprint("ai_qa", __name__)


# =========================
# PAGE
# =========================

@ai_qa_bp.route("/ai-qa-lab")
@login_required
@role_required("researcher", "admin")
def ai_qa_lab():
    return render_template("ai_qa_lab.html")


# =========================
# STATUS / HEALTH
# =========================

@ai_qa_bp.route("/api/ai_qa/status", methods=["GET"])
@login_required
@role_required("researcher", "admin")
def ai_qa_status():
    return jsonify({
        "status": "ok",
        "module": "AI QA Lab",
        "user": current_user.email,
        "role": current_user.role
    })


# =========================
# AI TEST ENDPOINT
# =========================

@csrf.exempt
@ai_qa_bp.route("/api/ai_qa/run_test", methods=["POST"])
@login_required
@role_required("researcher", "admin")
def run_test():

    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")

    if not session_id:
        return jsonify({
            "error": "Missing session_id"
        }), 400

    try:
        result = run_ai_analysis(session_id)

        return jsonify({
            "status": "ok",
            "session_id": session_id,
            "score": result.get("score"),
            "anomaly": result.get("anomaly"),
            "risk_level": result.get("risk_level"),
            "features": result.get("features"),
        })

    except Exception as e:
        traceback.print_exc()

        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500


# =========================
# AI TEST GENERATION
# =========================

@csrf.exempt
@ai_qa_bp.route("/api/ai_qa/generate_test", methods=["POST"])
@login_required
@role_required("researcher", "admin")
def generate_test():

    data = request.get_json(silent=True) or {}

    return jsonify({
        "status": "generated",
        "message": "AI QA test generation endpoint secured.",
        "input": data
    })


# =========================
# AI QA VALIDATION
# =========================

@csrf.exempt
@ai_qa_bp.route("/api/ai_qa/validate", methods=["POST"])
@login_required
@role_required("researcher", "admin")
def ai_qa_validate():

    data = request.get_json(silent=True) or {}

    return jsonify({
        "status": "validated",
        "message": "AI QA validation endpoint secured.",
        "input": data
    })


# =========================
# PLAYWRIGHT / QA PIPELINE TRIGGER
# =========================

@csrf.exempt
@ai_qa_bp.route("/api/qa/run_pipeline", methods=["POST"])
@login_required
@role_required("researcher", "admin")
@limiter.limit("5 per hour")
def run_pipeline():

    try:
        # 1. Run Playwright tests
        test_result = subprocess.run(
            ["npx", "playwright", "test"],
            cwd=os.getcwd(),
            capture_output=True,
            text=True
        )

        # 2. Run API checks
        api_result = subprocess.run(
            ["pytest", "tests/api"],
            cwd=os.getcwd(),
            capture_output=True,
            text=True
        )

        # 3. AI QA validation hook
        ai_result = subprocess.run(
            ["python", "-m", "tests.ai.run_ai_qa"],
            cwd=os.getcwd(),
            capture_output=True,
            text=True
        )

        success = (
            test_result.returncode == 0 and
            api_result.returncode == 0 and
            ai_result.returncode == 0
        )

        return jsonify({
            "status": "pipeline completed" if success else "pipeline failed",
            "success": success,
            "playwright": {
                "returncode": test_result.returncode,
                "stdout": test_result.stdout[-3000:],
                "stderr": test_result.stderr[-1000:]
            },
            "api": {
                "returncode": api_result.returncode,
                "stdout": api_result.stdout[-3000:],
                "stderr": api_result.stderr[-1000:]
            },
            "ai": {
                "returncode": ai_result.returncode,
                "stdout": ai_result.stdout[-3000:],
                "stderr": ai_result.stderr[-1000:]
            }
        })

    except Exception as e:
        traceback.print_exc()

        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500