# Telemetry Routes
# routes/telemetry_routes.py

from flask_login import login_required
from auth.decorators import role_required

from flask import (
    Blueprint,
    jsonify,
    request
)

from core.telemetry.telemetry_engine import (
    push_telemetry,
    get_latest_telemetry
)

from core.telemetry.telemetry_buffer import (
    load_telemetry_buffer
)

telemetry_bp = Blueprint(
    "telemetry",
    __name__
)


# =========================================================
# PUSH TELEMETRY
# =========================================================

@telemetry_bp.route("/api/push_telemetry", methods=["POST"])
@login_required
@role_required("operator", "admin")
def api_push_telemetry():

    data = request.json

    result = push_telemetry(data)

    return jsonify(result)


# =========================================================
# GET LATEST TELEMETRY
# =========================================================

@telemetry_bp.route("/api/telemetry")
@login_required
@role_required("viewer", "operator", "researcher", "admin")
def api_get_telemetry():

    data = get_latest_telemetry()

    return jsonify(data)


# =========================================================
# LOAD BUFFER
# =========================================================

@telemetry_bp.route("/api/telemetry_buffer")
@login_required
@role_required("operator", "researcher", "admin")
def api_telemetry_buffer():

    data = load_telemetry_buffer()

    return jsonify(data)