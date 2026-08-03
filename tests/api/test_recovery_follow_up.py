import unittest

from repositories.recovery_repository import normalize_recovery_follow_up_payload


class RecoveryFollowUpPayloadTests(unittest.TestCase):
    def test_normalizes_allowed_follow_up_values(self):
        payload = normalize_recovery_follow_up_payload(
            {
                "energy_level": "higher",
                "fatigue_level": "lower",
                "sleep_quality": "good",
                "discomfort": "none",
                "heart_rate_bpm": "62.4",
                "spo2": 98,
                "unexpected": "ignored",
            }
        )

        self.assertEqual(payload["energy_level"], "higher")
        self.assertEqual(payload["follow_up_window"], "one_hour")
        self.assertEqual(payload["heart_rate_bpm"], 62.4)
        self.assertEqual(payload["spo2"], 98.0)
        self.assertNotIn("unexpected", payload)

    def test_rejects_invalid_values_and_ranges(self):
        with self.assertRaises(ValueError):
            normalize_recovery_follow_up_payload({"sleep_quality": "excellent"})
        with self.assertRaises(ValueError):
            normalize_recovery_follow_up_payload({"heart_rate_bpm": 15})
        with self.assertRaises(ValueError):
            normalize_recovery_follow_up_payload({"spo2": 101})
        with self.assertRaises(ValueError):
            normalize_recovery_follow_up_payload({"follow_up_window": "later"})
