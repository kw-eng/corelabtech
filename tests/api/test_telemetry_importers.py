import tempfile
import unittest
from pathlib import Path

from core.telemetry.contract import canonicalize_telemetry_rows
from core.telemetry.device_catalog import device_catalog, resolve_device_capability
from services.importers.registry import get_importer


class TelemetryImporterTests(unittest.TestCase):
    def test_csv_importer_uses_the_shared_contract(self):
        importer = get_importer("csv")

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "oximeter.csv"
            path.write_text(
                "timestamp,pulse,spo2\n"
                "12:00:00 Jul 20 2026,68,98\n",
                encoding="utf-8",
            )
            rows = importer.import_data(path)

        self.assertEqual(importer.import_type, "csv")
        self.assertEqual(importer.parser_version, "csv-v2")
        self.assertEqual(rows[0]["pulse_rate_bpm"], 68.0)
        self.assertIsNone(rows[0]["heart_rate_bpm"])

    def test_unknown_importer_is_rejected_before_ingestion(self):
        with self.assertRaisesRegex(ValueError, "Unsupported telemetry"):
            get_importer("unsupported_device")

    def test_apple_health_xml_importer_keeps_watch_hrv_separate_from_rr(self):
        importer = get_importer("apple_health_xml")
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "export.xml"
            path.write_text(
                "<?xml version='1.0' encoding='UTF-8'?>\n"
                "<HealthData>\n"
                "<Record type='HKQuantityTypeIdentifierHeartRate' value='62' startDate='2026-08-01 10:00:00 +0200' sourceName='Apple Watch'/>\n"
                "<Record type='HKQuantityTypeIdentifierOxygenSaturation' value='0.98' startDate='2026-08-01 10:00:00 +0200' sourceName='Apple Watch'/>\n"
                "<Record type='HKQuantityTypeIdentifierHeartRateVariabilitySDNN' value='45' startDate='2026-08-01 10:00:00 +0200' sourceName='Apple Watch'/>\n"
                "</HealthData>",
                encoding="utf-8",
            )
            rows = importer.import_data(path)

        self.assertEqual(rows[0]["heart_rate_bpm"], 62.0)
        self.assertEqual(rows[0]["spo2"], 98.0)
        self.assertEqual(rows[0]["device_reported_hrv_sdnn_ms"], 45.0)
        self.assertEqual(rows[0]["rr_intervals"], [])
        self.assertEqual(rows[0]["measurement_method"], "ppg")

    def test_polar_csv_preserves_rr_packets_without_classifying_an_unknown_model(self):
        importer = get_importer("polar_csv")
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "polar.csv"
            path.write_text(
                "timestamp,heart rate,rr_ms\n"
                "2026-08-01T10:00:00+02:00,63,810;795\n",
                encoding="utf-8",
            )
            rows = importer.import_data(path)

        self.assertEqual(rows[0]["heart_rate_bpm"], 63.0)
        self.assertEqual(rows[0]["rr_intervals"], [810.0, 795.0])
        self.assertEqual(importer.parser_version, "polar-csv-v1")

    def test_health_connect_json_keeps_reported_hrv_separate_from_rr(self):
        importer = get_importer("health_connect_json")
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "health-connect.json"
            path.write_text(
                "{" 
                "\"records\":["
                "{\"type\":\"HeartRateRecord\",\"time\":\"2026-08-01T10:00:00Z\",\"value\":61},"
                "{\"type\":\"OxygenSaturationRecord\",\"time\":\"2026-08-01T10:00:00Z\",\"value\":0.98},"
                "{\"type\":\"HeartRateVariabilityRmssdRecord\",\"time\":\"2026-08-01T10:00:00Z\",\"value\":42}"
                "]}",
                encoding="utf-8",
            )
            rows = importer.import_data(path)

        self.assertEqual(rows[0]["heart_rate_bpm"], 61.0)
        self.assertEqual(rows[0]["spo2"], 98.0)
        self.assertEqual(rows[0]["device_reported_hrv_rmssd_ms"], 42.0)
        self.assertEqual(rows[0]["rr_intervals"], [])

    def test_device_catalog_keeps_watches_out_of_raw_rr_policy(self):
        apple_watch = resolve_device_capability("Apple Watch Ultra")

        self.assertEqual(apple_watch["device_type"], "watch_ppg")
        self.assertEqual(apple_watch["measurement_method"], "ppg")
        self.assertIn(
            "raw_rr_eligible",
            {entry["hrv_policy"] for entry in device_catalog()},
        )

    def test_canonical_sample_does_not_infer_heart_rate_from_ppg_pulse(self):
        row = canonicalize_telemetry_rows(
            [
                {
                    "timestamp": "2026-07-20T12:00:00",
                    "pulse": 68,
                    "pulse_rate_bpm": 68,
                    "spo2": 98,
                    "source": "pulseox",
                }
            ]
        )[0]

        self.assertIsNone(row["heart_rate_bpm"])
        self.assertEqual(row["pulse_rate_bpm"], 68)
        self.assertEqual(row["rr_intervals"], [])
        self.assertIn("respiration_rate", row)
        self.assertIn("signal_quality", row)


if __name__ == "__main__":
    unittest.main()
