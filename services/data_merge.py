def merge_during_phase(csv_data, fit_data, chamber_data):
    return {
        "time": fit_data["time"],
        "pulse": fit_data["pulse"],
        "hrv": fit_data["hrv"],
        "spo2": fit_data["spo2"],

        "chamber": {
            "pressure": chamber_data["pressure"],
            "ata": chamber_data["ata"],
            "oxygen": chamber_data["oxygen"]
        },

        "derived": {
            "stress_index": compute_stress(fit_data),
            "recovery_score": compute_recovery(fit_data)
        }
    }
def merge_during(fit, csv):

    merged = []

    for r in fit:
        merged.append({
            "time": r.get("timestamp"),
            "spo2": r.get("spo2"),
            "pulse": r.get("hr"),
            "hrv": r.get("hrv"),
            "source": "fit"
        })

    for r in csv:
        merged.append({
            "time": r.get("time"),
            "spo2": r.get("spo2"),
            "pulse": r.get("pulse"),
            "hrv": r.get("hrv"),
            "source": "csv"
        })

    merged.sort(
        key=lambda x: parse_time(x.get("time")) or datetime.min
    )

    return merged