import json
import unittest
from pathlib import Path

from services.session_response_presentation import (
    build_localized_session_response,
)


def catalog(locale):
    return json.loads(Path(f"translations/{locale}.json").read_text(encoding="utf-8"))


def complete_response():
    return {
        "pre": {"spo2": 97, "heart_rate_bpm": 70, "hrv_rmssd_ms": 40},
        "during": {"avg_spo2": 98, "min_spo2": 96, "avg_heart_rate_bpm": 68},
        "post": {"spo2": 98, "heart_rate_bpm": 68, "hrv_rmssd_ms": 45},
        "deltas": {"spo2_percentage_points": 1, "heart_rate_bpm": -2, "hrv_rmssd_ms": 5},
        "availability": {"available_delta_count": 3, "possible_delta_count": 3},
        "confidence": "high",
        "subjective_context": {"post": {"energy_level": "higher", "fatigue_level": "lower"}},
        "limitations": [],
    }


class SessionResponsePresentationTests(unittest.TestCase):
    def test_english_presentation_is_observational_and_localized(self):
        presentation = build_localized_session_response(complete_response(), catalog("en"))

        self.assertEqual(presentation["completeness"], "3 of 3 objective comparisons available")
        self.assertEqual(presentation["confidence"], "High")
        self.assertIn(
            "Post-session SpO2 was +1 pp higher",
            presentation["observations"][0],
        )
        self.assertNotIn("improved", " ".join(presentation["observations"]).lower())
        self.assertNotIn("report.", str(presentation))
        self.assertNotIn("Po sesji", str(presentation))

    def test_polish_presentation_has_no_english_leakage(self):
        presentation = build_localized_session_response(complete_response(), catalog("pl"))

        self.assertEqual(presentation["confidence"], "Wysoka")
        self.assertIn("Dostępne 3 z 3", presentation["completeness"])
        self.assertIn("Po sesji", presentation["observations"][0])
        self.assertNotIn("Post-session", str(presentation))
        self.assertNotIn("report.", str(presentation))

    def test_missing_data_and_subjective_only_response_are_visible(self):
        presentation = build_localized_session_response({
            "pre": {}, "during": {}, "post": {},
            "deltas": {"spo2_percentage_points": None, "heart_rate_bpm": None, "hrv_rmssd_ms": None},
            "availability": {"available_delta_count": 0, "possible_delta_count": 3},
            "confidence": "insufficient",
            "subjective_context": {"post": {"energy_level": "higher"}},
            "limitations": ["pre_measurements_unavailable", "post_measurements_unavailable"],
        }, catalog("en"))

        self.assertEqual(presentation["completeness"], "0 of 3 objective comparisons available")
        self.assertEqual(presentation["confidence"], "Insufficient")
        self.assertEqual(presentation["subjective"][0]["value"], "Higher")
        self.assertTrue(any(
            "HRV (RMSSD) PRE/POST comparison unavailable" in value
            for value in presentation["limitations"]
        ))


if __name__ == "__main__":
    unittest.main()
