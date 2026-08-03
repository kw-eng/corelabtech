import unittest

from core.telemetry.device_catalog import (
    DEVICE_COMPATIBILITY_VERSION,
    device_compatibility_matrix,
)


class DeviceCompatibilityMatrixTests(unittest.TestCase):
    def test_matrix_has_a_versioned_set_of_25_unique_device_records(self):
        devices = device_compatibility_matrix()

        self.assertEqual(DEVICE_COMPATIBILITY_VERSION, "device-compatibility-v1")
        self.assertEqual(len(devices), 25)
        self.assertEqual(len({device["id"] for device in devices}), len(devices))

    def test_each_record_declares_import_and_data_provenance(self):
        required = {
            "manufacturer",
            "model",
            "formats",
            "raw_rr",
            "reported_hrv",
            "timestamps",
            "official_api",
            "cloud_account",
            "support_level",
            "import_types",
            "verification_status",
            "source_url",
        }

        for device in device_compatibility_matrix():
            self.assertTrue(required.issubset(device))
            self.assertIn(device["raw_rr"], {"yes", "no", "conditional"})
            self.assertIn(device["reported_hrv"], {"yes", "no", "conditional"})
            self.assertIn(device["support_level"], {"core", "trend", "planned"})

    def test_reported_hrv_devices_do_not_claim_raw_rr(self):
        reported_hrv_devices = [
            device
            for device in device_compatibility_matrix()
            if device["analysis_role"] == "reported_hrv_and_trend_only"
        ]

        self.assertTrue(reported_hrv_devices)
        self.assertTrue(all(device["raw_rr"] == "no" for device in reported_hrv_devices))

    def test_only_anonymized_checkme_export_is_declared_verified(self):
        verified_ids = {
            device["id"]
            for device in device_compatibility_matrix()
            if device["verification_status"] == "verified"
        }

        self.assertSetEqual(verified_ids, {"checkme-o2"})


if __name__ == "__main__":
    unittest.main()
