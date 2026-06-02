# Telemetry Buffer
import json
import os
from datetime import datetime

BUFFER_FILE = "data/telemetry_buffer.json"

os.makedirs("data", exist_ok=True)


# =========================
# LOAD BUFFER
# =========================
def load_telemetry_buffer():

    if not os.path.exists(BUFFER_FILE):
        return []

    try:
        with open(BUFFER_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    except Exception:
        return []


# =========================
# SAVE BUFFER
# =========================
def save_telemetry_buffer(buffer):

    with open(BUFFER_FILE, "w", encoding="utf-8") as f:
        json.dump(buffer, f, indent=2)


# =========================
# APPEND TELEMETRY
# =========================
def append_telemetry(data):

    buffer = load_telemetry_buffer()

    payload = {
        "timestamp": datetime.utcnow().isoformat(),
        **data
    }

    buffer.append(payload)

    # keep last 1000 records
    buffer = buffer[-1000:]

    save_telemetry_buffer(buffer)

    return payload


# =========================
# CLEAR BUFFER
# =========================
def clear_telemetry_buffer():

    save_telemetry_buffer([])


# =========================
# GET LATEST
# =========================
def get_latest_buffer_record():

    buffer = load_telemetry_buffer()

    if not buffer:
        return {}

    return buffer[-1]