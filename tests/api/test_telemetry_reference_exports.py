"""Regression checks for anonymized and schema-level telemetry exports."""

from __future__ import annotations

import unittest
from pathlib import Path

from services.importers.registry import get_importer


PROJECT_ROOT = Path(__file__).resolve().parents[2]

REFERENCE_EXPORTS = (
    {
        "id": "garmin-hrm600-fit",
        "kind": "anonymized_reference_export",
        "import_type": "fit",
        "path": "files/hrm600/2026-06-24-21-01-16.fit",
        "minimum_rows": 1,
        "signals": {"heart_rate_bpm", "rr_intervals"},
    },
    {
        "id": "garmin-fenix8-fit",
        "kind": "anonymized_reference_export",
        "import_type": "fit",
        "path": "files/fenix8/23664778759_ACTIVITY.fit",
        "minimum_rows": 1,
        "signals": {"heart_rate_bpm", "rr_intervals"},
    },
    {
        "id": "checkme-o2-csv",
        "kind": "anonymized_reference_export",
        "import_type": "csv",
        "path": "files/checkme/Checkme O2 _20260720130928.csv",
        "minimum_rows": 1,
        "signals": {"pulse_rate_bpm", "spo2"},
    },
    {
        "id": "polar-csv-schema",
        "kind": "schema_fixture",
        "import_type": "polar_csv",
        "path": "tests/fixtures/telemetry/polar_h10_rr.csv",
        "minimum_rows": 2,
        "signals": {"heart_rate_bpm", "rr_intervals"},
    },
    {
        "id": "apple-health-xml-schema",
        "kind": "schema_fixture",
        "import_type": "apple_health_xml",
        "path": "tests/fixtures/telemetry/apple_health_export.xml",
        "minimum_rows": 1,
        "signals": {
            "heart_rate_bpm",
            "spo2",
            "device_reported_hrv_sdnn_ms",
        },
    },
    {
        "id": "health-connect-json-schema",
        "kind": "schema_fixture",
        "import_type": "health_connect_json",
        "path": "tests/fixtures/telemetry/health_connect_export.json",
        "minimum_rows": 1,
        "signals": {
            "heart_rate_bpm",
            "spo2",
            "device_reported_hrv_rmssd_ms",
        },
    },
)


class TelemetryReferenceExportTests(unittest.TestCase):
    def test_every_registered_import_type_has_a_reference_export(self):
        registered = {"fit", "csv", "polar_csv", "apple_health_xml", "health_connect_json"}
        covered = {entry["import_type"] for entry in REFERENCE_EXPORTS}

        self.assertSetEqual(covered, registered)

    def test_reference_exports_produce_the_declared_signals(self):
        for export in REFERENCE_EXPORTS:
            with self.subTest(export=export["id"]):
                path = PROJECT_ROOT / export["path"]
                self.assertTrue(path.is_file(), f"Missing reference export: {path}")

                rows = get_importer(export["import_type"]).import_data(path)

                self.assertGreaterEqual(len(rows), export["minimum_rows"])
                for signal in export["signals"]:
                    if signal == "rr_intervals":
                        self.assertTrue(any(row.get(signal) for row in rows), signal)
                    else:
                        self.assertTrue(
                            any(row.get(signal) is not None for row in rows),
                            signal,
                        )

    def test_reported_hrv_fixtures_never_invent_raw_rr(self):
        for export in REFERENCE_EXPORTS:
            if export["import_type"] not in {"apple_health_xml", "health_connect_json"}:
                continue
            with self.subTest(export=export["id"]):
                rows = get_importer(export["import_type"]).import_data(
                    PROJECT_ROOT / export["path"]
                )
                self.assertTrue(all(not row["rr_intervals"] for row in rows))


if __name__ == "__main__":
    unittest.main()
