import unittest

from core.telemetry.capability_scanner import scan_telemetry_rows


class CapabilityScannerTests(unittest.TestCase):
    def test_detects_signals_quality_and_analysis_without_device_model(self):
        report = scan_telemetry_rows(
            [
                {
                    "timestamp": "2026-08-04T10:00:00+00:00",
                    "heart_rate_bpm": 62,
                    "rr_intervals": [810, 795],
                    "motion": 0,
                },
                {
                    "timestamp": "2026-08-04T10:00:01+00:00",
                    "heart_rate_bpm": 63,
                    "rr_intervals": [800],
                    "motion": 0,
                },
            ],
            file_type="fit",
            source_type="wearable_telemetry",
        )

        self.assertTrue(report["signals"]["timestamp"])
        self.assertTrue(report["signals"]["rr_intervals"])
        self.assertTrue(report["analysis"]["available"]["hrv_analysis"])
        self.assertEqual(report["quality"]["gaps_detected"], 0)
        self.assertEqual(report["file"]["source_type"], "wearable_telemetry")


if __name__ == "__main__":
    unittest.main()
