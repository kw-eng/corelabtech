import unittest

from services.hrv_pipeline import (
    calculate_hrv_from_rr,
    calculate_hrv_phase_metrics,
    calculate_hrv_windows,
    requires_hrv_recalculation,
)


APPROVED_RR_SOURCE = {
    "hr_source_type": "chest_hrm",
    "hr_measurement_method": "ecg",
}


class HrvPipelineTests(unittest.TestCase):
    def test_normalizes_fit_seconds_and_calculates_metrics(self):
        metrics = calculate_hrv_from_rr(
            [
                {"rr_interval": value, **APPROVED_RR_SOURCE}
                for value in (0.8, 0.82, 0.79, 0.85, 0.81, 0.84) * 4
            ]
        )

        self.assertEqual(metrics["hrv_algorithm_version"], "rr-clean-v2")
        self.assertEqual(metrics["rr_count"], 24)
        self.assertIsNotNone(metrics["rmssd"])
        self.assertIsNotNone(metrics["sdnn"])
        self.assertTrue(metrics["hrv_usable_for_scoring"])

    def test_excludes_out_of_range_and_large_rr_artifacts(self):
        metrics = calculate_hrv_from_rr(
            [
                {"rr_interval": value, **APPROVED_RR_SOURCE}
                for value in (800, 810, 5000, 805, 1400, 800)
            ]
        )

        self.assertEqual(metrics["rr_raw_count"], 6)
        self.assertEqual(metrics["rr_artifact_count"], 2)
        self.assertEqual(metrics["rr_count"], 4)

    def test_device_reported_hrv_cannot_replace_raw_rr(self):
        metrics = calculate_hrv_from_rr([])

        self.assertEqual(metrics["hrv_confidence"], "unavailable")
        self.assertIsNone(metrics["rmssd"])
        self.assertFalse(metrics["hrv_usable_for_scoring"])

    def test_rr_from_unapproved_source_is_excluded_from_hrv(self):
        metrics = calculate_hrv_from_rr(
            [{"rr_interval": 800, "hr_source_type": "wearable_fit"}]
        )

        self.assertEqual(metrics["rr_raw_count"], 0)
        self.assertEqual(metrics["rr_source_rejected_count"], 1)
        self.assertIsNone(metrics["rmssd"])

    def test_calculates_windows_and_configured_session_phases(self):
        rows = [
            {
                "timestamp": f"2026-07-29T10:0{index // 6}:{(index % 6) * 10:02d}",
                "rr_interval": 800 if index % 2 == 0 else 850,
                **APPROVED_RR_SOURCE,
            }
            for index in range(12)
        ]
        segments = [
            {"phase": "compression", "actual_duration_min": 1},
            {"phase": "exposure", "actual_duration_min": 1},
        ]

        windows = calculate_hrv_windows(rows, session_segments=segments)
        phases = calculate_hrv_phase_metrics(rows, session_segments=segments)

        self.assertEqual([item["phase"] for item in phases], ["compression", "exposure"])
        self.assertEqual(len(windows), 2)
        self.assertTrue(all(item["rr_count"] == 6 for item in windows))

    def test_detects_features_that_need_hrv_recalculation(self):
        self.assertTrue(requires_hrv_recalculation("rr-clean-v0"))
        self.assertFalse(requires_hrv_recalculation("rr-clean-v2"))


if __name__ == "__main__":
    unittest.main()
