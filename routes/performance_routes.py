from flask import Blueprint, jsonify, request

from flask_login import login_required

from auth.decorators import role_required

from services.performance_service import (
    run_gatling_test,
    get_performance_history,
    get_latest_performance_result,
)

from security.csrf import csrf
from security.limiter import limiter

import traceback


performance_bp = Blueprint(
    "performance",
    __name__
)


# =========================================
# RUN PERFORMANCE TEST
# ADMIN ONLY
# =========================================

@csrf.exempt
@performance_bp.route(
    "/api/performance/run",
    methods=["POST"]
)
@login_required
@role_required("admin")
@limiter.limit("10 per hour")
def run_performance():

    data = request.get_json(
        silent=True
    ) or {}

    test_type = data.get(
        "type",
        "sessions"
    )

    allowed = [
        "sessions",
        "merge",
        "analysis",
        "csv",
        "fit"
    ]

    if test_type not in allowed:

        return jsonify({
            "status": "error",
            "error": "invalid performance test type",
            "allowed": allowed,
            "received": test_type
        }), 400

    try:

        result = run_gatling_test(
            test_type
        )

        if not isinstance(result, dict):

            return jsonify({
                "status": "error",
                "error": "performance service returned invalid result",
                "raw": str(result),
                "test_type": test_type
            }), 500

        result.setdefault(
            "test_type",
            test_type
        )

        result.setdefault(
            "status",
            "success"
            if result.get("returncode") == 0
            else "error"
        )

        return jsonify(result)

    except Exception as e:

        traceback.print_exc()

        return jsonify({
            "status": "error",
            "error": str(e),
            "test_type": test_type
        }), 500


# =========================================
# LATEST RESULT
# RESEARCHER + ADMIN
# =========================================

@performance_bp.route(
    "/api/performance/latest"
)
@login_required
@role_required(
    "researcher",
    "admin"
)
def performance_latest():

    try:

        return jsonify(
            get_latest_performance_result()
        )

    except Exception as e:

        traceback.print_exc()

        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500


# =========================================
# HISTORY
# RESEARCHER + ADMIN
# =========================================

@performance_bp.route(
    "/api/performance/history"
)
@login_required
@role_required(
    "researcher",
    "admin"
)
def performance_history():

    try:

        return jsonify({
            "status": "ok",
            "history":
                get_performance_history()
        })

    except Exception as e:

        traceback.print_exc()

        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500