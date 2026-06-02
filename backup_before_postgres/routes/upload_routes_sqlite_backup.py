# routes/upload_routes.py

from flask import (
    Blueprint,
    request,
    jsonify
)

import os
import traceback

from services.fit_parser import (
    parse_fit_file
)

from services.csv_parser import (
    parse_csv_file
)

upload_bp = Blueprint(
    "upload",
    __name__
)

# =========================================================
# PATHS
# =========================================================

FIT_DIR = "data/uploads/fit"
CSV_DIR = "data/uploads/csv"

os.makedirs(FIT_DIR, exist_ok=True)
os.makedirs(CSV_DIR, exist_ok=True)

# =========================================================
# UPLOAD FIT
# =========================================================

@upload_bp.route("/upload_fit", methods=["POST"])
def upload_fit():

    try:

        file = request.files.get("file")

        session_id = request.form.get(
            "session_id"
        )

        print("FIT SESSION:", session_id)

        if not file:

            return jsonify({
                "error": "No FIT file"
            }), 400

        filename = file.filename

        print("FIT FILE:", filename)

        path = os.path.join(
            FIT_DIR,
            filename
        )

        file.save(path)

        print("FIT SAVED:", path)

        print("START FIT PARSE")

        rows = parse_fit_file(path)

        print("PARSE DONE")
        print(rows[:3] if rows else "NO ROWS")

        print("FIT RECORDS:", len(rows))

        if len(rows) == 0:

            return jsonify({

                "status": "uploaded",

                "warning":
                    "FIT parsed but no telemetry records found",

                "records": 0,

                "file": filename
            })

        return jsonify({

            "status": "uploaded",

            "records": len(rows),

            "file": filename
        })

    except Exception as e:

        print("UPLOAD FIT ERROR:")
        print(str(e))

        traceback.print_exc()

        return jsonify({

            "error": str(e)

        }), 500

# =========================================================
# UPLOAD CSV
# =========================================================

@upload_bp.route("/upload_csv", methods=["POST"])
def upload_csv():

    try:

        file = request.files.get("file")

        session_id = request.form.get(
            "session_id"
        )

        print("CSV SESSION:", session_id)

        if not file:

            return jsonify({
                "error": "No CSV file"
            }), 400

        filename = file.filename

        print("CSV FILE:", filename)

        path = os.path.join(
            CSV_DIR,
            filename
        )

        file.save(path)

        print("CSV SAVED:", path)

        rows = parse_csv_file(path)

        print("CSV RECORDS:", len(rows))

        if len(rows) == 0:

            return jsonify({

                "status": "uploaded",

                "warning":
                    "CSV loaded but no valid rows detected",

                "records": 0,

                "file": filename
            })

        return jsonify({

            "status": "uploaded",

            "records": len(rows),

            "file": filename
        })

    except Exception as e:

        print("UPLOAD CSV ERROR:")
        print(str(e))

        traceback.print_exc()

        return jsonify({

            "error": str(e)

        }), 500