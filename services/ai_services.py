# services/ai_service.py

from services.telemetry_merge import (
    merge_telemetry,
    summarize_merged
)


def analyze_session(
    fit_data,
    csv_data,
    chamber_data
):

    merged = merge_telemetry(
        fit_data,
        csv_data,
        chamber_data
    )

    summary = summarize_merged(merged)

    score = 100
    anomaly = "NONE"

    avg_hrv = summary.get("avg_hrv")
    avg_spo2 = summary.get("avg_spo2")

    # LOW HRV
    if avg_hrv and avg_hrv < 25:

        score -= 25
        anomaly = "LOW_HRV"

    # HYPOXIA
    if avg_spo2 and avg_spo2 < 90:

        score -= 35
        anomaly = "HYPOXIA"

    # HBOT STRESS
    if (
        chamber_data.get("pressure_ata", 0) > 2.4
        and avg_hrv
        and avg_hrv < 20
    ):

        score -= 20
        anomaly = "HBOT_STRESS"

    score = max(score, 0)

    return {

        "score": score,

        "anomaly": anomaly,

        "summary":
            f"Avg HRV: {avg_hrv}, "
            f"Avg SpO2: {avg_spo2}",

        "merged_samples":
            len(merged)
    }