# routes/qa_routes.py

import traceback

from flask import (
    Blueprint,
    render_template,
    jsonify
)

from flask_login import login_required

from auth.decorators import role_required
from security.csrf import csrf
from security.limiter import limiter

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
@login_required
@role_required("researcher", "admin")
def qa_lab():

    return render_template(
        "qa_lab.html"
    )


# =========================================================
# RUN PLAYWRIGHT
# ADMIN ONLY
# =========================================================

@csrf.exempt
@qa_bp.route("/api/qa/run_playwright", methods=["POST"])
@login_required
@role_required("admin")
@limiter.limit("10 per hour")
def run_playwright():

    try:

        result = run_playwright_tests()

        return jsonify(result)

    except Exception as e:

        traceback.print_exc()

        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500


# =========================================================
# RUN FULL QA LOOP
# ADMIN ONLY
# =========================================================

@csrf.exempt
@qa_bp.route("/api/qa/run_qa_loop", methods=["POST"])
@login_required
@role_required("admin")
@limiter.limit("5 per hour")
def run_full_qa():

    try:

        result = run_qa_loop()

        return jsonify(result)

    except Exception as e:

        traceback.print_exc()

        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500