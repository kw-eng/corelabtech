# routes/qa_routes.py

from flask import (
    Blueprint,
    render_template,
    jsonify
)

from core.qa.playwright_runner import (
    run_playwright_tests
)

from core.qa.qa_loop import (
    run_qa_loop
)

qa_bp = Blueprint("qa", __name__)


# =========================================================
# QA LAB PAGE
# =========================================================

@qa_bp.route("/qa")
def qa_lab():

    return render_template(
        "qa_lab.html"
    )


# =========================================================
# RUN PLAYWRIGHT
# =========================================================

@qa_bp.route("/api/run_playwright")
def run_playwright():

    result = run_playwright_tests()

    return jsonify(result)


# =========================================================
# RUN FULL QA LOOP
# =========================================================

@qa_bp.route("/api/run_qa_loop")
def run_full_qa():

    result = run_qa_loop()

    return jsonify(result)