# model analizy fizjologii (prosty model AI)


def analyze_physiology(spo2, pulse, hrv, body_temp=None, chamber_temp=None):

    # =========================
    # DEFAULT OUTPUT (PRO)
    # =========================
    result = {
        "data_quality": "OK",
        "oxygen": "NO DATA",
        "pulse": "NO DATA",
        "hrv": "NO DATA",
        "body_temp": "NO DATA",
        "environment": "NO DATA",
    }

    # =========================
    # SPO2 ANALYSIS
    # =========================
    if spo2 is not None:
        if spo2 < 80 or spo2 > 100:
            result["oxygen"] = "INVALID"
            result["data_quality"] = "ERROR"
    elif spo2 < 90:
        result["oxygen"] = "HYPOXIA"
    elif spo2 < 94:
        result["oxygen"] = "LOW"
    else:
        result["oxygen"] = "OPTIMAL"

    # =========================
    # PULSE ANALYSIS
    # =========================
    if pulse is not None:
        if pulse < 30 or pulse > 220:
            result["pulse"] = "INVALID"
            result["data_quality"] = "ERROR"
    elif pulse > 140:
        result["pulse"] = "HIGH"
    elif pulse < 50:
        result["pulse"] = "LOW"
    else:
        result["pulse"] = "NORMAL"

    # =========================
    # HRV ANALYSIS
    # =========================
    if hrv is not None:
        if hrv < 0 or hrv > 200:
            result["hrv"] = "INVALID"
            result["data_quality"] = "ERROR"
    elif hrv < 30:
        result["hrv"] = "LOW (STRESS)"
    elif hrv > 80:
        result["hrv"] = "HIGH (RECOVERY)"
    else:
        result["hrv"] = "NORMAL"

    # =========================
    # BODY TEMPERATURE
    # =========================
    if body_temp is not None:
        if body_temp < 34 or body_temp > 42:
            result["body_temp"] = "INVALID"
            result["data_quality"] = "ERROR"
    elif body_temp > 37.5:
        result["body_temp"] = "ELEVATED"
    elif body_temp < 35.5:
        result["body_temp"] = "LOW"
    else:
        result["body_temp"] = "NORMAL"

    # =========================
    # CHAMBER TEMPERATURE
    # =========================
    if chamber_temp is not None:
        if chamber_temp < 10 or chamber_temp > 50:
            result["environment"] = "INVALID"
            result["data_quality"] = "ERROR"
    elif chamber_temp > 26:
        result["environment"] = "HOT"
    elif chamber_temp < 18:
        result["environment"] = "COLD"
    else:
        result["environment"] = "OPTIMAL"

    # =========================
    # 🔥 GLOBAL INTERPRETATION
    # =========================
    if result["data_quality"] == "ERROR":
        result["summary"] = "INVALID DATA"
    else:
        if result["oxygen"] in ["HYPOXIA", "LOW"]:
            result["summary"] = "LOW OXYGEN RESPONSE"
        elif result["hrv"] == "LOW (STRESS)":
            result["summary"] = "STRESS RESPONSE"
        elif result["hrv"] == "HIGH (RECOVERY)" and result["oxygen"] == "OPTIMAL":
            result["summary"] = "GOOD HBOT RESPONSE"
        else:
            result["summary"] = "NORMAL RESPONSE"


# =========================
# 🔥 AI SCORE (PRO)
# =========================
    score = 50

    if result["oxygen"] == "OPTIMAL":
     score += 20

    if result["hrv"] == "HIGH (RECOVERY)":
     score += 20

    if result["pulse"] == "NORMAL":
     score += 10

    result["score"] = min(score, 100)

    return result