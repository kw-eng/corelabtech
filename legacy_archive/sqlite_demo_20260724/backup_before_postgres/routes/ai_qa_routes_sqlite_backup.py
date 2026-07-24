  # routes/ai_qa_routes.py

from flask import Blueprint, render_template, request, jsonify

# 🔥 import logiki AI (dopasuj do swojego projektu)
from services.ai_engine import run_ai_analysis

ai_qa_bp = Blueprint("ai_qa", __name__)

# =========================
# PAGE
# =========================
@ai_qa_bp.route("/ai-qa-lab")
def ai_qa_lab():
    return render_template("ai_qa_lab.html")


# =========================
# AI TEST (NAJWAŻNIEJSZY ENDPOINT)
# =========================
@ai_qa_bp.route("/api/ai_qa/run_test", methods=["POST"])
def run_test():

    data = request.json
    session_id = data.get("session_id")

    if not session_id:
        return jsonify({"error": "Missing session_id"}), 400

    try:
        result = run_ai_analysis(session_id)

        return jsonify({
            "score": result.get("score"),
            "anomaly": result.get("anomaly")
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
    # PLAYWRIGHT TEST PIPELINE TRIGGER
@ai_qa_bp.route("/api/qa/run_pipeline", methods=["POST"])
def run_pipeline():

    import subprocess

    # 1. run tests
    test_result = subprocess.run(
        ["npx", "playwright", "test"],
        capture_output=True,
        text=True
    )

    # 2. run API checks
    api_result = subprocess.run(
        ["pytest", "tests/api"],
        capture_output=True,
        text=True
    )

    # 3. AI QA validation hook
    ai_result = subprocess.run(
        ["python", "-m", "tests.ai.run_ai_qa"],
        capture_output=True,
        text=True
    )

    return jsonify({
        "playwright": test_result.stdout[-1000:],
        "api": api_result.stdout[-1000:],
        "ai": ai_result.stdout[-1000:],
        "status": "pipeline completed"
    })