# Telemetry Engine
from core.telemetry.telemetry_buffer import (
    append_telemetry,
    get_latest_buffer_record,
    load_telemetry_buffer
)

# =========================
# PUSH TELEMETRY
# =========================
def push_telemetry(
    spo2=None,
    pulse=None,
    hrv=None,
    ata=None,
    temperature=None
):

    payload = {
        "spo2": spo2,
        "pulse": pulse,
        "hrv": hrv,
        "ata": ata,
        "temperature": temperature
    }

    # anomaly / alert detection
    payload["alert"] = detect_telemetry_alert(payload)

    append_telemetry(payload)

    return payload


# =========================
# GET LATEST TELEMETRY
# =========================
def get_latest_telemetry():

    return get_latest_buffer_record()


# =========================
# LOAD FULL HISTORY
# =========================
def get_telemetry_history():

    return load_telemetry_buffer()


# =========================
# ALERT ENGINE
# =========================
def detect_telemetry_alert(data):

    spo2 = data.get("spo2")
    pulse = data.get("pulse")
    hrv = data.get("hrv")
    ata = data.get("ata")

    alerts = []

    # =========================
    # HYPOXIA
    # =========================
    if spo2 is not None and spo2 < 88:
        alerts.append("HYPOXIA")

    # =========================
    # TACHYCARDIA
    # =========================
    if pulse is not None and pulse > 120:
        alerts.append("TACHYCARDIA")

    # =========================
    # LOW HRV
    # =========================
    if hrv is not None and hrv < 20:
        alerts.append("LOW_HRV")

    # =========================
    # HIGH PRESSURE
    # =========================
    if ata is not None and ata > 2.4:
        alerts.append("HIGH_ATA")

    if len(alerts) == 0:
        return "NORMAL"

    return ",".join(alerts)