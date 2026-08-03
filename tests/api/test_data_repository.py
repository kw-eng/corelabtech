import unittest
import sys
import types


psycopg2 = types.ModuleType("psycopg2")
psycopg2_extras = types.ModuleType("psycopg2.extras")
psycopg2_extras.execute_values = lambda *args, **kwargs: None
psycopg2.extras = psycopg2_extras
sys.modules.setdefault("psycopg2", psycopg2)
sys.modules.setdefault("psycopg2.extras", psycopg2_extras)

from repositories import data_repository
from repositories.data_repository import create_csv_import, insert_fit_measurements


class CapturingCursor:
    def __init__(self):
        self.query = ""
        self.params = ()

    def execute(self, query, params):
        self.query = query
        self.params = params

    def fetchone(self):
        return (42,)


class CsvImportRepositoryTests(unittest.TestCase):
    def test_csv_import_metadata_binds_every_sql_placeholder(self):
        cursor = CapturingCursor()

        import_id = create_csv_import(
            cursor,
            session_id="session-1",
            user_id="client-1",
            filename="telemetry.csv",
            file_hash="hash",
            records_parsed=3,
            device="Checkme O2",
            parser_version="csv-v2",
            device_type="finger_oximeter",
            device_model="checkme_o2",
            measurement_method="ppg",
            telemetry_schema_version="telemetry-v1",
            source_timezone="Europe/Warsaw",
            timestamp_normalization_version="timestamp-v1",
        )

        self.assertEqual(import_id, 42)
        self.assertEqual(cursor.query.count("%s"), len(cursor.params))


class FitMeasurementRepositoryTests(unittest.TestCase):
    def test_fit_insert_keeps_reported_hrv_without_an_undefined_value(self):
        captured = {}
        original_execute_values = data_repository.execute_values

        def capture_execute_values(_cursor, _query, values, **_kwargs):
            captured["values"] = values

        data_repository.execute_values = capture_execute_values
        try:
            saved = insert_fit_measurements(
                CapturingCursor(),
                import_id=1,
                session_id="session-1",
                user_id="client-1",
                filename="wearable.fit",
                rows=[
                    {
                        "timestamp": "2026-08-01T10:00:00Z",
                        "heart_rate_bpm": 62,
                        "device_reported_hrv_sdnn_ms": 45,
                    }
                ],
                telemetry_metadata={
                    "device_type": "wearable_fit",
                    "measurement_method": "unknown",
                    "signal_quality": "unknown",
                    "quality_reason": "device_measurement_method_not_confirmed",
                },
            )
        finally:
            data_repository.execute_values = original_execute_values

        self.assertEqual(saved, 1)
        self.assertEqual(captured["values"][0][9], 45)


if __name__ == "__main__":
    unittest.main()
