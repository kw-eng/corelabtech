import os
import unittest
from unittest.mock import patch

from services.trend_narration import (
    build_trend_ai_view,
    build_trend_fact_sheet,
)


class TrendNarrationTests(unittest.TestCase):
    def test_fact_sheet_excludes_identity_and_unverified_rows(self):
        series = {
            "user_id": "PRIVATE_CLIENT",
            "series_limit": 10,
            "analyses": [
                {
                    "session_id": "PRIVATE_SESSION",
                    "summary": "Do not expose prior narrative",
                    "data_quality_score": 90,
                    "avg_hrv": 50,
                    "avg_spo2": 98,
                    "avg_reference_heart_rate": 60,
                    "total_duration_min": 60,
                },
                {
                    "session_id": "PRIVATE_SESSION_2",
                    "data_quality_score": 40,
                    "avg_hrv": 20,
                },
            ],
            "data_quality_engine": {"warning_counts": {"missing_spo2": 1}},
        }

        facts = build_trend_fact_sheet(series)

        self.assertEqual(facts["series"]["eligible_sessions"], 1)
        self.assertNotIn("PRIVATE_CLIENT", str(facts))
        self.assertNotIn("PRIVATE_SESSION", str(facts))
        self.assertNotIn("Do not expose", str(facts))

    def test_deterministic_view_blocks_trend_with_too_few_eligible_sessions(self):
        view = build_trend_ai_view(
            {
                "series_limit": 5,
                "analyses": [
                    {"data_quality_score": 90, "avg_hrv": 50},
                    {"data_quality_score": 50, "avg_hrv": 40},
                ],
            }
        )

        self.assertEqual(view["version"], "trend-ai-v1")
        self.assertEqual(view["status"], "disabled")
        self.assertIn("Brak wystarczajacej liczby sesji", view["text"])

    def test_llm_is_disabled_by_default(self):
        with patch.dict(os.environ, {"LLM_TREND_NARRATION_ENABLED": "false"}):
            view = build_trend_ai_view({"analyses": []})

        self.assertEqual(view["source"], "deterministic_fallback")
