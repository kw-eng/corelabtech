# hypoxia
# tachycardia
# stress response
def detect_anomaly(spo2, pulse, hrv):

    if spo2 is not None and spo2 < 90:
        return "HYPOXIA ALERT"

    if pulse is not None and pulse > 140:
        return "HIGH HEART RATE"

    if hrv is not None and hrv < 20:
        return "STRESS ALERT"

        return "NORMAL"


# anomaly_detection.py
# Prosta detekcja anomalii telemetrycznych


def detect_anomalies(spo2, pulse, hrv, temperature):

    anomalies = []

    if spo2 < 90:
        anomalies.append("Low SpO2")

    if pulse > 120:
        anomalies.append("High heart rate")

    if hrv < 20:
        anomalies.append("Low HRV")

    if temperature > 38:
        anomalies.append("High temperature")

    if len(anomalies) == 0:
        anomalies.append("No anomalies detected")

    return anomalies
