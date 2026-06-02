from flask import Blueprint, jsonify
from datetime import datetime
import time
import os

from database_postgres import db


health_bp = Blueprint(
    "health",
    __name__
)

START_TIME = time.time()


@health_bp.route("/api/health")
def health():

    result = {
        "status": "ok",
        "service": "CoreLabTech",
        "version": "1.0.0",
        "environment": os.getenv(
            "APP_ENV",
            "development"
        ),
        "database": "unknown",
        "database_latency_ms": None,
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

        result["status"] = "error"
        result["database"] = "error"
        result["error"] = str(e)

        return jsonify(result), 500

    finally:

        if c:
            c.close()

        if con:
            con.close()

    return jsonify(result)