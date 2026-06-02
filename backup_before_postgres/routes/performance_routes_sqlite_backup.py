from flask import Blueprint, jsonify, request
from services.performance_service import (
    run_gatling_test,
    get_performance_history,
    get_latest_performance_result,
)

performance_bp = Blueprint(
    "performance_bp",
    __name__
)


@performance_bp.route("/api/performance/run", methods=["POST"])
def run_performance():
    data = request.json or {}

    test_type = data.get("type")

    result = run_gatling_test(test_type)

    return jsonify(result)


@performance_bp.route("/api/performance/latest")
def performance_latest():
    return jsonify(get_latest_performance_result())


@performance_bp.route("/api/performance/history")
def performance_history():
    return jsonify({
        "status": "ok",
        "history": get_performance_history()
    })