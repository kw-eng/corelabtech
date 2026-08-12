import unittest
from services.analysis_service import (
    analyze_measurements,
    get_analysis_model_manifest,
)


class AnalysisSummaryTests(unittest.TestCase):
    def test_admin_model_manifest_tracks_active_analysis_versions(self):
        manifest = get_analysis_model_manifest()

        self.assertEqual(manifest["version"], "wellness-rules-v2")
        self.assertEqual(manifest["hrv_algorithm_version"], "rr-clean-v2")
        self.assertEqual(len(manifest["layers"]), 4)
        self.assertEqual(manifest["llm_narration"]["version"], "llm-narration-v2")

    def test_summary_mentions_pulse_hrv_and_check_in_context(self):
        measurements = [
            {
                "timestamp": "2026-07-29T10:00:00",
                "spo2": 98,
                "pulse": 58,
                "heart_rate": 60,
                "hrv": 57.9,
                "rr_interval": 800,
                "synchronized": True,
            },
            {
                "timestamp": "2026-07-29T10:00:05",
                "spo2": 98,
                "pulse": 60,
                "heart_rate": 61,
                "hrv": 59.1,
                "rr_interval": 820,
                "synchronized": True,
            },
            {
                "timestamp": "2026-07-29T10:00:10",
                "spo2": 97,
                "pulse": 59,
                "heart_rate": 62,
                "hrv": 58.5,
                "rr_interval": 810,
                "synchronized": True,
            },
            {
                "timestamp": "2026-07-29T10:00:15",
                "spo2": 98,
                "pulse": 57,
                "heart_rate": 59,
                "hrv": 56.5,
                "rr_interval": 790,
                "synchronized": True,
            },
            {
                "timestamp": "2026-07-29T10:00:20",
                "spo2": 98,
                "pulse": 58,
                "heart_rate": 60,
                "hrv": 57.0,
                "rr_interval": 805,
                "synchronized": True,
            },
        ]
        for row in measurements:
            row["hr_source_type"] = "chest_hrm"
            row["hr_measurement_method"] = "ecg"
        session_context = {
            "pre_check_in": {
                "sleep_hours": 5.5,
                "sleep_quality": "poor",
                "training_load_24h": "hard",
                "stress_level": "high",
                "fatigue_level": "high",
            },
            "post_check_out": {
                "energy_level": "higher",
                "relaxation_level": "high",
                "fatigue_level": "lower",
            },
        }

        result = analyze_measurements(
            measurements=measurements,
            usable=measurements,
            session_context=session_context,
        )

        summary = result["summary"]

        self.assertIn("Pulse, wearable heart rate and HRV", summary)
        self.assertIn("Average HRV", summary)
        self.assertIn("Check-in context", summary)
        self.assertIn("reduced sleep quality", summary)
        self.assertIn("higher recent activity load", summary)
        self.assertIn("reported stress or fatigue", summary)

    def test_sensor_divergence_reduces_confidence_not_wellness_score(self):
        measurements = [
            {
                "timestamp": f"2026-07-29T10:01:{index * 5:02d}",
                "spo2": 98,
                "heart_rate_bpm": 70,
                "pulse_rate_bpm": 40,
                "rr_interval": 800 if index % 2 == 0 else 900,
                "synchronized": True,
                "time_alignment_quality": "high",
                "hr_source_type": "chest_hrm",
                "hr_measurement_method": "ecg",
            }
            for index in range(12)
        ]

        result = analyze_measurements(
            measurements=measurements,
            usable=measurements,
        )

        features = result["features"]
        self.assertEqual(result["overall_score"], 100)
        self.assertFalse(result["session_flagged"])
        self.assertTrue(result["sensor_alignment_warning"])
        self.assertEqual(result["analysis_confidence"], "low")
        self.assertEqual(features["median_hr_pulse_difference_bpm"], 30.0)
        self.assertEqual(features["hr_pulse_agreement_percent"], 0.0)
        self.assertEqual(features["hr_pulse_divergence_duration_seconds"], 55.0)
        self.assertEqual(features["synchronized_temporal_coverage_percent"], 100.0)
        self.assertIn("low_hr_pulse_agreement", features["quality_reasons"])

    def test_unknown_wearable_hr_is_not_used_for_wellness_scoring(self):
        measurements = [
            {
                "timestamp": "2026-07-29T10:01:00",
                "spo2": 98,
                "heart_rate_bpm": 170,
                "synchronized": True,
                "hr_source_type": "wearable_fit",
                "hr_measurement_method": "unknown",
            }
        ]

        result = analyze_measurements(
            measurements=measurements,
            usable=measurements,
        )

        self.assertEqual(result["overall_score"], 100)
        self.assertFalse(result["wellness_flags"]["elevated_load"])
        self.assertEqual(result["features"]["max_reference_heart_rate"], None)


if __name__ == "__main__":
    unittest.main()
