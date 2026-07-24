from flask import Blueprint, current_app, jsonify
from datetime import datetime
import time
import os

from database_postgres import db
from services.logger_service import error_logger


health_bp = Blueprint(
    "health",
    __name__
)

START_TIME = time.time()


@health_bp.route("/api/health")
def health():
    environment = os.getenv(
        "APP_ENV",
        "development"
    )
    is_production = environment.lower() == "production"
    cors_origins = [
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "").split(",")
        if origin.strip()
    ]

    result = {
        "status": "ok",
        "service": "CoreLabTech",
        "version": "1.0.0",
        "environment": environment,
        "database": "unknown",
        "database_latency_ms": None,
        "checks": {
            "debug_routes_disabled": not current_app.config.get(
                "DEBUG_ROUTES_ENABLED",
                False,
            ),
            "cors_configured": bool(cors_origins) or not is_production,
            "secure_cookies": bool(
                current_app.config.get("SESSION_COOKIE_SECURE")
            ) or not is_production,
            "rate_limiter_expected": os.getenv(
                "PERFORMANCE_TESTING",
                "false",
            ).lower() != "true",
        },
        "uptime_seconds": round(
            time.time() - START_TIME,
            2
        ),
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }

    con = None
    c = None

    try:

        start = time.time()

        con = db()
        c = con.cursor()

        c.execute("SELECT 1")
        c.fetchone()

        latency_ms = round(
            (time.time() - start) * 1000,
            2
        )

        result["database"] = "ok"
        result["database_latency_ms"] = latency_ms

    except Exception as e:
        error_logger.exception("Health check database failure")

        result["status"] = "error"
        result["database"] = "error"
        result["error"] = (
            "database_unavailable"
            if is_production
            else str(e)
        )

        return jsonify(result), 500

    finally:

        if c:
            c.close()

        if con:
            con.close()

    return jsonify(result)
