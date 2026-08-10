import tempfile
import unittest
from pathlib import Path
import sys
import types


sys.modules.setdefault(
    "database_postgres",
    types.SimpleNamespace(db=lambda: None),
)
sys.modules.setdefault(
    "repositories.data_repository",
    types.SimpleNamespace(
        get_latest_completed_csv_import=lambda *args, **kwargs: None,
        get_latest_completed_fit_import=lambda *args, **kwargs: None,
        load_csv=lambda *args, **kwargs: [],
        load_fit=lambda *args, **kwargs: [],
    ),
)
merge_repository = sys.modules.setdefault(
    "repositories.merge_repository",
    types.SimpleNamespace(),
)
for name, value in {
    "complete_merge_job": lambda *args, **kwargs: None,
    "create_merge_job": lambda *args, **kwargs: 1,
    "get_latest_completed_merge_job": lambda *args, **kwargs: None,
    "insert_merged_measurements": lambda *args, **kwargs: 0,
    "load_merged_measurements": lambda *args, **kwargs: [],
}.items():
    if not hasattr(merge_repository, name):
        setattr(merge_repository, name, value)
sys.modules.setdefault(
    "repositories.analysis_repository",
    types.SimpleNamespace(
        complete_ai_result=lambda *args, **kwargs: None,
        create_ai_result=lambda *args, **kwargs: 1,
    ),
)
sys.modules.setdefault(
    "repositories.wellness_repository",
    types.SimpleNamespace(
        get_wellness_summary=lambda *args, **kwargs: {},
        refresh_daily_baseline=lambda *args, **kwargs: None,
        upsert_session_features=lambda *args, **kwargs: None,
    ),
)

from services.analysis_service import analyze_measurements
from services.csv_parser import parse_csv_file
from services.data_merge import merge_csv_only, merge_fit_and_csv
from services.telemetry_time import normalize_rows_timestamps
from services.hrv_pipeline import annotate_hrv_rmssd_timeline
from core.telemetry.device_catalog import resolve_fit_device, resolve_garmin_product


class TelemetryProvenanceTests(unittest.TestCase):
    def test_time_normalization_preserves_source_value_and_uses_utc_when_known(self):
        rows = normalize_rows_timestamps(
            [{"timestamp": "2026-07-20T12:00:00"}],
            source_timezone="Europe/Warsaw",
        )

        self.assertEqual(rows[0]["original_timestamp"], "2026-07-20T12:00:00")
        self.assertEqual(rows[0]["source_timezone"], "Europe/Warsaw")
        self.assertEqual(rows[0]["timestamp_utc"].isoformat(), "2026-07-20T10:00:00+00:00")

    def test_only_known_chest_straps_are_classified_as_ecg(self):
        self.assertEqual(
            resolve_fit_device("Polar H10")["measurement_method"], "ecg"
        )
        self.assertEqual(
            resolve_fit_device("Garmin Fenix 8")["measurement_method"],
            "unknown",
        )

    def test_known_garmin_product_id_identifies_an_external_hrm(self):
        self.assertEqual(resolve_garmin_product(4607), "Garmin HRM 600")
        self.assertIsNone(resolve_garmin_product(4536))

    def test_rr_from_a_known_chest_hrm_produces_a_display_rmssd_series(self):
        rows = [
            {
                "timestamp": "2026-07-20T12:00:00",
                "rr_intervals": [0.80],
                "hr_source_type": "chest_hrm",
                "hr_measurement_method": "ecg",
            },
            {
                "timestamp": "2026-07-20T12:00:01",
                "rr_intervals": [0.82, 0.79],
                "hr_source_type": "chest_hrm",
                "hr_measurement_method": "ecg",
            },
        ]

        annotate_hrv_rmssd_timeline(rows)

        self.assertIsNone(rows[0]["hrv"])
        self.assertIsNotNone(rows[1]["hrv"])
        self.assertGreater(rows[1]["hrv"], 0)

    def test_pulse_oximeter_csv_does_not_promote_pulse_to_heart_rate(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "oximeter.csv"
            path.write_text(
                "timestamp,pulse,spo2\n"
                "12:00:00 Jul 20 2026,68,98\n",
                encoding="utf-8",
            )

            rows = parse_csv_file(path)

        self.assertEqual(rows[0]["pulse_rate_bpm"], 68.0)
        self.assertIsNone(rows[0]["heart_rate_bpm"])
        self.assertNotIn("heart_rate", rows[0])

    def test_csv_only_merge_preserves_pulse_as_ppg_auxiliary_measurement(self):
        merged = merge_csv_only(
            csv_rows=[
                {
                    "timestamp": "2026-07-20T12:00:00",
                    "pulse": 68,
                    "pulse_rate_bpm": 68,
                    "heart_rate": 68,
                    "spo2": 98,
                    "device_type": "finger_oximeter",
                    "measurement_method": "ppg",
                    "signal_quality": "medium",
                }
            ]
        )

        self.assertIsNone(merged[0]["heart_rate_bpm"])
        self.assertEqual(merged[0]["pulse_rate_bpm"], 68)
        self.assertEqual(merged[0]["pulse_source_type"], "finger_oximeter")
        self.assertEqual(merged[0]["pulse_measurement_method"], "ppg")

    def test_fit_and_csv_merge_preserves_each_signal_provenance(self):
        merged = merge_fit_and_csv(
            fit_rows=[
                {
                    "timestamp": "2026-07-20T12:00:00",
                    "heart_rate": 66,
                    "heart_rate_bpm": 66,
                    "hrv": 42,
                    "rr_interval": 900,
                    "device_type": "wearable_fit",
                    "measurement_method": "unknown",
                    "signal_quality": "unknown",
                }
            ],
            csv_rows=[
                {
                    "timestamp": "2026-07-20T12:00:00",
                    "pulse": 67,
                    "pulse_rate_bpm": 67,
                    "spo2": 98,
                    "motion": 0,
                    "device_type": "finger_oximeter",
                    "measurement_method": "ppg",
                    "signal_quality": "medium",
                }
            ],
            tolerance_ms=2500,
        )

        self.assertEqual(merged[0]["heart_rate_bpm"], 66)
        self.assertEqual(merged[0]["pulse_rate_bpm"], 67)
        self.assertEqual(merged[0]["hr_source_type"], "wearable_fit")
        self.assertEqual(merged[0]["pulse_source_type"], "finger_oximeter")
        self.assertEqual(merged[0]["time_alignment_method"], "offset_nearest")
        self.assertEqual(merged[0]["time_alignment_quality"], "medium")

    def test_fit_and_csv_merge_prefers_utc_when_both_sources_are_normalized(self):
        merged = merge_fit_and_csv(
            fit_rows=[
                {
                    "timestamp": "2026-07-20T12:00:00",
                    "timestamp_utc": "2026-07-20T10:00:00+00:00",
                    "heart_rate": 66,
                    "heart_rate_bpm": 66,
                    "hrv": 42,
                    "rr_interval": 900,
                    "device_type": "chest_hrm",
                    "measurement_method": "ecg",
                    "signal_quality": "high",
                }
            ],
            csv_rows=[
                {
                    "timestamp": "2026-07-20T12:00:00",
                    "timestamp_utc": "2026-07-20T10:00:00+00:00",
                    "pulse": 67,
                    "pulse_rate_bpm": 67,
                    "spo2": 98,
                    "motion": 0,
                    "device_type": "finger_oximeter",
                    "measurement_method": "ppg",
                    "signal_quality": "medium",
                }
            ],
            tolerance_ms=2500,
        )

        self.assertEqual(merged[0]["time_alignment_method"], "utc_nearest")
        self.assertEqual(merged[0]["time_alignment_quality"], "high")
        self.assertIsNotNone(merged[0]["timestamp_utc"])

    def test_analysis_does_not_treat_ppg_pulse_as_reference_heart_rate(self):
        rows = merge_csv_only(
            csv_rows=[
                {
                    "timestamp": "2026-07-20T12:00:00",
                    "pulse": 145,
                    "pulse_rate_bpm": 145,
                    "spo2": 98,
                    "device_type": "finger_oximeter",
                    "measurement_method": "ppg",
                    "signal_quality": "medium",
                }
            ]
        )

        result = analyze_measurements(measurements=rows, usable=rows)

        self.assertIsNone(result["features"]["max_heart_rate"])
        self.assertEqual(result["features"]["max_pulse"], 145.0)
        self.assertFalse(result["wellness_flags"]["sensor_alignment_warning"])

    def test_analysis_does_not_use_device_hrv_without_raw_rr(self):
        rows = [
            {
                "timestamp": "2026-07-20T12:00:00",
                "spo2": 98,
                "heart_rate_bpm": 65,
                "hrv": 10,
                "synchronized": True,
                "time_alignment_quality": "high",
                "hr_source_type": "chest_hrm",
            }
        ]

        result = analyze_measurements(measurements=rows, usable=rows)

        self.assertIsNone(result["features"]["avg_hrv"])
        self.assertEqual(result["features"]["device_reported_hrv"], 10.0)
        self.assertFalse(result["stress_detected"])


if __name__ == "__main__":
    unittest.main()
