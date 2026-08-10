import unittest

from repositories.realtime_telemetry_repository import normalize_realtime_payload


class RealtimeTelemetryPayloadTests(unittest.TestCase):
    def test_normalizes_supported_measurements_without_hrv(self):
        payload = normalize_realtime_payload(
            {
                "pulse": "72",
                "spo2": 98,
                "ata": 1.5,
                "source_type": "finger_oximeter",
                "measurement_method": "ppg",
                "signal_quality": "medium",
                "hrv": 12,
            }
        )
        self.assertEqual(payload["pulse_rate_bpm"], 72.0)
        self.assertEqual(payload["spo2"], 98.0)
        self.assertEqual(payload["pressure_ata"], 1.5)
        self.assertNotIn("hrv", payload)

    def test_rejects_invalid_values_and_empty_payloads(self):
        with self.assertRaisesRegex(ValueError, "spo2"):
            normalize_realtime_payload({"spo2": 120})
        with self.assertRaisesRegex(ValueError, "at least one"):
            normalize_realtime_payload({"source_type": "watch_ppg"})


if __name__ == "__main__":
    unittest.main()
