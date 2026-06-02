# services/telemetry_merge.py

from statistics import mean


def merge_telemetry(fit_data, csv_data, chamber):

    merged = []

    csv_index = 0

    for fit in fit_data:

        timestamp = fit.get("timestamp")

        csv_row = None

        while csv_index < len(csv_data):

            candidate = csv_data[csv_index]

            csv_row = candidate
            csv_index += 1
            break

        merged.append({

            "timestamp": timestamp,

            "hr": fit.get("pulse"),

            "rr": fit.get("rr"),

            "hrv": fit.get("hrv"),

            "spo2":
                csv_row.get("spo2")
                if csv_row else None,

            "pulse_external":
                csv_row.get("pulse")
                if csv_row else None,

            "pressure_ata":
                chamber.get("pressure_ata"),

            "oxygen_percent":
                chamber.get("oxygen_mask_percent"),

            "humidity":
                chamber.get("humidity"),

            "temperature":
                chamber.get("chamber_temperature")
        })

    return merged


def summarize_merged(data):

    if not data:
        return {}

    hrv = [
        x["hrv"]
        for x in data
        if x.get("hrv")
    ]

    spo2 = [
        x["spo2"]
        for x in data
        if x.get("spo2")
    ]

    hr = [
        x["hr"]
        for x in data
        if x.get("hr")
    ]

    return {

        "avg_hrv":
            round(mean(hrv), 2)
            if hrv else None,

        "avg_spo2":
            round(mean(spo2), 2)
            if spo2 else None,

        "avg_hr":
            round(mean(hr), 2)
            if hr else None,

        "samples":
            len(data)
    }