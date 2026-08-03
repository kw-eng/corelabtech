import os
import unittest
from unittest.mock import patch

from services.llm_narration import (
    build_session_fact_sheet,
    narrate_fact_sheet,
)


class LlmNarrationTests(unittest.TestCase):
    def test_fact_sheet_excludes_client_identity_and_raw_telemetry(self):
        fact_sheet = build_session_fact_sheet(
            {
                "client_id": "CLIENT_PRIVATE",
                "model_name": "CoreLabTech Wellness Session Analysis",
                "model_version": "wellness-rules-v2",
                "wellness_response_score": 90,
                "wellness_status": "baseline",
                "quality_warnings": ["low_match_rate"],
                "features": {
                    "avg_spo2": 98,
                    "rr_count": 42,
                    "raw_payload": {"timestamp": "private"},
                },
            }
        )

        self.assertNotIn("client_id", fact_sheet)
        self.assertNotIn("raw_payload", str(fact_sheet))
        self.assertEqual(fact_sheet["schema_version"], "wellness-fact-sheet-v2")
        self.assertEqual(fact_sheet["measurements"]["avg_spo2"], 98)

    def test_disabled_provider_returns_deterministic_fallback(self):
        fact_sheet = build_session_fact_sheet(
            {
                "quality_warnings": ["insufficient_rr_for_hrv"],
                "wellness_status": "baseline",
                "wellness_disclaimer": "Wellness only.",
            }
        )

        with patch.dict(os.environ, {"LLM_NARRATION_ENABLED": "false"}):
            result = narrate_fact_sheet(fact_sheet)

        self.assertEqual(result.status, "disabled")
        self.assertIn("insufficient_rr_for_hrv", result.text)
        self.assertIn("Wellness only.", result.text)

    def test_fact_sheet_includes_only_derived_session_comparison(self):
        fact_sheet = build_session_fact_sheet(
            {
                "session_comparison": {
                    "version": "session-comparison-v1",
                    "comparisons": {"5": {"reference_sessions": 3}},
                },
                "features": {"raw_rows": [{"secret": "not exported"}]},
            }
        )

        self.assertEqual(
            fact_sheet["session_comparison"]["version"],
            "session-comparison-v1",
        )
        self.assertNotIn("raw_rows", str(fact_sheet))


if __name__ == "__main__":
    unittest.main()
