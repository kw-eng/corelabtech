import unittest

from services.series_service import build_longitudinal_response_intelligence
from services.wellness_response import build_session_response


class WellnessResponseTests(unittest.TestCase):
    def test_builds_objective_deltas_and_keeps_subjective_context_separate(self):
        response = build_session_response(
            session_context={
                "pre_check_in": {"spo2": 97, "pulse": 70, "fatigue_level": "high"},
                "post_check_out": {"spo2": 98, "pulse": 68, "fatigue_level": "lower", "energy_level": "higher"},
            },
            features={"avg_spo2": 97.5, "avg_hrv": 42, "match_rate": 95},
            data_quality_score=88,
            analysis_confidence="high",
            quality_warnings=[],
        )

        self.assertEqual(response["deltas"]["spo2_percentage_points"], 1)
        self.assertEqual(response["deltas"]["heart_rate_bpm"], -2)
        self.assertIsNone(response["deltas"]["hrv_rmssd_ms"])
        self.assertEqual(response["subjective_context"]["post"]["fatigue_level"], "lower")
        self.assertNotIn("fatigue_level", response["post"])
        self.assertEqual(response["confidence"], "high")
        self.assertEqual(response["availability"]["available_delta_count"], 2)
        self.assertEqual(response["availability"]["possible_delta_count"], 3)

    def test_one_objective_delta_cannot_have_high_confidence(self):
        response = build_session_response(
            session_context={
                "pre_check_in": {"spo2": 97},
                "post_check_out": {"spo2": 98},
            },
            features={},
            data_quality_score=95,
            analysis_confidence="high",
            quality_warnings=[],
        )

        self.assertEqual(response["availability"]["available_delta_count"], 1)
        self.assertEqual(response["confidence"], "medium")

    def test_normalizes_numeric_strings_and_rejects_invalid_measurements(self):
        numeric = build_session_response(
            session_context={
                "pre_check_in": {"spo2": "97", "pulse": "70"},
                "post_check_out": {"spo2": "98", "pulse": "68"},
            },
            features={},
            data_quality_score="85",
            analysis_confidence="high",
            quality_warnings=[],
        )
        invalid = build_session_response(
            session_context={
                "pre_check_in": {"spo2": "not-a-number"},
                "post_check_out": {"spo2": "98"},
            },
            features={},
            data_quality_score=85,
            analysis_confidence="high",
            quality_warnings=[],
        )

        self.assertEqual(numeric["pre"]["spo2"], 97)
        self.assertIsInstance(numeric["post"]["spo2"], int)
        self.assertEqual(numeric["deltas"]["spo2_percentage_points"], 1)
        self.assertIsNone(invalid["deltas"]["spo2_percentage_points"])

    def test_missing_pre_or_post_is_unavailable_not_zero(self):
        response = build_session_response(
            session_context={"pre_check_in": {"spo2": 97}, "post_check_out": {}},
            features={}, data_quality_score=90, analysis_confidence="high", quality_warnings=[],
        )

        self.assertIsNone(response["deltas"]["spo2_percentage_points"])
        self.assertEqual(response["confidence"], "insufficient")
        self.assertIn("post_measurements_unavailable", response["limitations"])

    def test_longitudinal_summary_tracks_metric_and_subjective_coverage(self):
        summary = build_longitudinal_response_intelligence([
            {"session_response": {"deltas": {"spo2_percentage_points": 1, "heart_rate_bpm": -2, "hrv_rmssd_ms": None}, "subjective_context": {"post": {"energy_level": "higher", "fatigue_level": "lower"}}}},
            {"session_response": {"deltas": {"spo2_percentage_points": None, "heart_rate_bpm": -4, "hrv_rmssd_ms": 5}, "subjective_context": {"post": {"energy_level": "higher", "discomfort": "none"}}}},
            {"session_response": {"deltas": {"spo2_percentage_points": None, "heart_rate_bpm": None, "hrv_rmssd_ms": None}, "subjective_context": {"post": {"fatigue_level": "lower", "relaxation_level": "high"}}}},
        ])

        self.assertEqual(summary["qualifying_sessions"], 2)
        self.assertEqual(summary["objective_qualifying_sessions"], 2)
        self.assertEqual(summary["subjective_qualifying_sessions"], 3)
        self.assertEqual(summary["total_sessions"], 3)
        self.assertEqual(summary["average_deltas"]["spo2_percentage_points"], 1.0)
        self.assertEqual(summary["average_deltas"]["heart_rate_bpm"], -3.0)
        self.assertEqual(summary["average_deltas"]["hrv_rmssd_ms"], 5.0)
        self.assertEqual(summary["metric_coverage"], {
            "spo2_percentage_points": 1,
            "heart_rate_bpm": 2,
            "hrv_rmssd_ms": 1,
        })
        self.assertEqual(summary["self_reported_counts"]["lower_fatigue"], 2)
        self.assertEqual(summary["self_reported_coverage"]["energy_level"], 2)
        self.assertEqual(summary["self_reported_coverage"]["fatigue_level"], 2)


if __name__ == "__main__":
    unittest.main()
