# services/ai_engine.py
# AI ENGINE
#    ↓
# run_ai_analysis()
#    ↓
# ├── ai_logs.json  ← dataset (ML / flaky)
# ├── explanation
# └── output

#    ↓

# TEST GENERATOR
#    ↓
# ├── Playwright test
# ├── TAGS (anomaly/hrv/spo2)
# └── assertions

import statistics,json,os

from ai.anomaly_detection import detect_anomaly
from ai.hbot_prediction import predict_hbot_response
from ai.physiology_ai import analyze_physiology


# =====================================================
# 🔥 PUBLIC API (USED BY ROUTES)
# =====================================================
def run_ai_analysis(spo2, pulse, hrv, ata=None, temp=None):
    """
    🔥 Central AI entrypoint (used by API)
    """

    anomaly = detect_anomaly(spo2, pulse, hrv)

    prediction = predict_hbot_response(spo2, pulse, hrv, ata)

    physiology = analyze_physiology(
        spo2,
        pulse,
        hrv,
        body_temp=None,
        chamber_temp=temp
    )

    explanation = _build_explanation(spo2, pulse, hrv, ata)

    return {
        "anomaly": anomaly,
        "prediction": prediction,
        "physiology": physiology,
        "explanation": explanation
    }
    # =========================
    # 🔥 AI LOGGING (dataset for ML + flaky detection)
    # =========================
    os.makedirs("data", exist_ok=True)

    with open("data/ai_logs.json", "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "input": {
                "spo2": spo2,
                "pulse": pulse,
                "hrv": hrv,
                "ata": ata,
                "temp": temp
            },
            "output": {
                "anomaly": anomaly,
                "prediction": prediction,
                "explanation": explanation
            }
        }) + "\n")

# =====================================================
# 🔥 EXPLAIN ENGINE (WHY FAILED)
# =====================================================
def _build_explanation(spo2, pulse, hrv, ata):
    explanation = []

    if spo2 is not None and spo2 < 92:
        explanation.append("Low oxygen level (SpO2 < 92)")

    if spo2 is not None and spo2 < 88:
        explanation.append("Severe hypoxia risk")

    if hrv is not None and hrv < 30:
        explanation.append("Low HRV → stress / poor recovery")

    if pulse is not None and pulse > 110:
        explanation.append("Elevated heart rate")

    if ata is not None and ata > 1.6:
        explanation.append("High chamber pressure")

    if not explanation:
        explanation.append("Parameters within optimal range")

    return explanation


# =====================================================
# 🔥 CORE ENGINE CLASS (QA + TIMESERIES + MERGE)
# =====================================================
class AIEngine:
    """
    Core AI engine for:
    - QA (flaky detection)
    - timeseries scoring
    - telemetry merging
    """

    # =========================
    # MAIN ENTRY (LEGACY / QA)
    # =========================
    def run(self, rows, mode="selected"):

        if not rows:
            return self._empty_response("no data")

        spo2, pulse, hrv, ata = self._extract(rows)

        score = self._calculate_score(spo2, pulse, hrv, ata)
        anomaly = self._detect_anomaly(spo2, pulse, hrv, ata)

        return {
            "score": score,
            "anomaly": anomaly,
            "mode": mode,
            "summary": "AI analysis complete",
            "stats": {
                "spo2_avg": self._avg(spo2),
                "pulse_avg": self._avg(pulse),
                "hrv_avg": self._avg(hrv),
                "ata_avg": self._avg(ata),
            }
        }

    # =========================
    # 🔥 TIMESERIES (REAL POWER)
    # =========================
    def run_timeseries(self, rows):

        if not rows:
            return self._empty_response("no data")

        scores = []

        for i, r in enumerate(rows):

            score = 50
            weight = 1 + (i / len(rows))  # recent bias

            if r.get("spo2", 0) > 94:
                score += 20

            if r.get("hrv", 0) > 50:
                score += 15

            if r.get("pulse", 0) < 90:
                score += 10

            score *= weight
            scores.append(score)

        final_score = sum(scores) / len(scores)

        anomaly = any(r.get("spo2", 0) < 90 for r in rows)

        return {
            "score": round(final_score, 2),
            "anomaly": anomaly,
            "trend": "stable" if final_score > 70 else "unstable"
        }

    # =========================
    # 🔥 FLAKY DETECTOR
    # =========================
    def run_qa_test(self, session_data):

        if not session_data:
            return {"error": "no data"}

        spo2 = self._pluck(session_data, "spo2")

        flaky = False
        if len(spo2) >= 3:
            flaky = statistics.pstdev(spo2) > 3

        score = self._calculate_score(
            spo2,
            self._pluck(session_data, "pulse"),
            self._pluck(session_data, "hrv"),
            self._pluck(session_data, "ata"),
        )

        return {
            "score": score,
            "flaky": flaky,
            "valid": score > 60
        }

    # =========================
    # 🔥 MERGE HELPERS
    # =========================
    def merge_fit_csv(self, fit_rows=None, csv_rows=None):

        merged = []

        if fit_rows:
            merged.extend(self._normalize_fit(fit_rows))

        if csv_rows:
            merged.extend(self._normalize_csv(csv_rows))

        merged.sort(key=lambda x: x.get("time", 0))

        return merged

    # =========================
    # INTERNALS
    # =========================
    def _calculate_score(self, spo2, pulse, hrv, ata):
        score = 50

        if spo2 and min(spo2) > 94:
            score += 20

        if hrv and self._avg(hrv) > 50:
            score += 20

        if pulse and self._avg(pulse) < 90:
            score += 10

        if ata and self._avg(ata) > 1.5:
            score += 10

        return min(score, 100)

    def _detect_anomaly(self, spo2, pulse, hrv, ata):
        if spo2 and min(spo2) < 90:
            return True
        if hrv and min(hrv) < 10:
            return True
        return False

    def _extract(self, rows):
        spo2, pulse, hrv, ata = [], [], [], []

        for r in rows:
            try:
                if isinstance(r, (list, tuple)):
                    spo2.append(r[0])
                    pulse.append(r[1])
                    hrv.append(r[2])
                    ata.append(r[3])
                else:
                    spo2.append(r.get("spo2"))
                    pulse.append(r.get("pulse"))
                    hrv.append(r.get("hrv"))
                    ata.append(r.get("ata"))
            except:
                continue

        return spo2, pulse, hrv, ata

    def _normalize_fit(self, rows):
        return [
            {
                "time": r.get("timestamp"),
                "spo2": r.get("spo2"),
                "pulse": r.get("hr"),  # 🔥 FIX: hr → pulse
                "hrv": r.get("hrv"),
                "source": "fit"
            }
            for r in rows
        ]

    def _normalize_csv(self, rows):
        return [
            {
                "time": r.get("time"),
                "spo2": r.get("spo2"),
                "pulse": r.get("pulse"),
                "hrv": r.get("hrv"),
                "source": "csv"
            }
            for r in rows
        ]

    def _pluck(self, data, key):
        return [d.get(key) for d in data if d.get(key) is not None]

    def _avg(self, arr):
        return sum(arr) / len(arr) if arr else 0

    def _empty_response(self, msg):
        return {
            "score": 0,
            "anomaly": False,
            "summary": msg
        }