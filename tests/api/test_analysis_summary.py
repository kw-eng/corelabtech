import unittest
import sys
import types

sys.modules.setdefault(
    "database_postgres",
    types.SimpleNamespace(db=lambda: None),
)
sys.modules.setdefault(
    "repositories.analysis_repository",
    types.SimpleNamespace(
        complete_ai_result=lambda *args, **kwargs: None,
        create_ai_result=lambda *args, **kwargs: 1,
    ),
)
sys.modules.setdefault(
    "repositories.merge_repository",
    types.SimpleNamespace(
        get_latest_completed_merge_job=lambda *args, **kwargs: None,
        load_merged_measurements=lambda *args, **kwargs: [],
    ),
)
sys.modules.setdefault(
    "repositories.wellness_repository",
    types.SimpleNamespace(
        refresh_daily_baseline=lambda *args, **kwargs: None,
        upsert_session_features=lambda *args, **kwargs: None,
    ),
)
from services.analysis_service import analyze_measurements


class AnalysisSummaryTests(unittest.TestCase):
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

        self.assertIn("Pulse, wearable HR and HRV", summary)
        self.assertIn("average HRV", summary)
        self.assertIn("Check-in context", summary)
        self.assertIn("reduced sleep quality", summary)
        self.assertIn("higher recent activity load", summary)
        self.assertIn("reported stress or fatigue", summary)


if __name__ == "__main__":
    unittest.main()
