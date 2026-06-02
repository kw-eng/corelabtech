def explain_anomaly(spo2, pulse, hrv, ata):

    reasons = []

    # ================= SPO2 =================
    if spo2:
        if min(spo2) < 90:
            reasons.append("SpO2 dropped below 90% (hypoxia risk)")
        elif sum(spo2)/len(spo2) < 94:
            reasons.append("Average SpO2 below optimal range")

    # ================= HRV =================
    if hrv:
        if min(hrv) < 25:
            reasons.append("HRV dropped significantly (stress response)")
        elif sum(hrv)/len(hrv) < 30:
            reasons.append("Low HRV indicates fatigue or poor recovery")

    # ================= PULSE =================
    if pulse:
        if max(pulse) > 120:
            reasons.append("Elevated heart rate detected")
        elif min(pulse) < 50:
            reasons.append("Abnormally low heart rate detected")

    # ================= PRESSURE =================
    if ata:
        if max(ata) > 1.6:
            reasons.append("High pressure exposure (>1.6 ATA)")

    # ================= DEFAULT =================
    if not reasons:
        reasons.append("No significant anomalies detected")

    return reasons