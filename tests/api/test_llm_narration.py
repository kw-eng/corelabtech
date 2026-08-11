import os
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from services.llm_narration import (
    build_session_fact_sheet,
    localized_deterministic_summary,
    narrate_fact_sheet,
)


def catalog(locale: str) -> dict[str, str]:
    return json.loads(Path(f"translations/{locale}.json").read_text(encoding="utf-8"))


def analysis_with_session_context() -> dict:
    return {
        "wellness_status": "baseline",
        "analysis_confidence": "moderate",
        "wellness_disclaimer": "Wellness only.",
        "features": {
            "signal_quality": "high",
            "session_context": {
                "pre_check_in": {
                    "spo2": 97,
                    "pulse": 70,
                    "sleep_hours": 7,
                    "sleep_quality": "fair",
                    "stress_level": "low",
                    "training_load_24h": "light",
                    "fatigue_level": "low",
                    "session_goal": "recovery",
                },
                "post_check_out": {
                    "spo2": 98,
                    "pulse": 68,
                    "energy_level": "higher",
                    "relaxation_level": "moderate",
                    "fatigue_level": "lower",
                    "discomfort": "none",
                },
                "session_timing": {
                    "compression_time_min": 10,
                    "exposure_time_min": 50,
                    "decompression_time_min": 10,
                },
            },
        },
    }


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
        self.assertEqual(fact_sheet["schema_version"], "wellness-fact-sheet-v3")
        self.assertEqual(fact_sheet["measurements"]["avg_spo2"], 98)
        self.assertIn("session_response", fact_sheet)

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

    def test_localized_summary_uses_actual_check_in_and_recovery_context(self):
        summary = localized_deterministic_summary(
            build_session_fact_sheet(analysis_with_session_context()), catalog("en")
        )

        self.assertIn("Check-in\nSpO2: 97%; Pulse / HR: 70 bpm", summary)
        self.assertIn("Check-out\nSpO2: 98%; Pulse / HR: 68 bpm", summary)
        self.assertIn("Sleep quality: Fair", summary)
        self.assertIn("Energy level: Higher", summary)
        self.assertNotIn("No data available for this part", summary)

    def test_localized_summary_uses_truthful_missing_message(self):
        summary = localized_deterministic_summary(
            build_session_fact_sheet({"features": {}}), catalog("en")
        )

        self.assertIn("No data available for this part of the session", summary)

    def test_dashboard_deterministic_summary_uses_active_locale(self):
        fact_sheet = build_session_fact_sheet(analysis_with_session_context())
        english = localized_deterministic_summary(fact_sheet, catalog("en"))
        polish = localized_deterministic_summary(fact_sheet, catalog("pl"))

        self.assertIn("Data limitations", english)
        self.assertIn("Summary", english)
        self.assertIn("Wellness and educational insight only", english)
        self.assertNotIn("Ograniczenia danych", english)
        self.assertIn("Ograniczenia danych", polish)
        self.assertIn("Podsumowanie", polish)
        self.assertIn("Jakość snu: Umiarkowana", polish)

    def test_localized_summary_never_leaks_report_translation_keys(self):
        for locale in ("en", "pl"):
            summary = localized_deterministic_summary(
                build_session_fact_sheet(analysis_with_session_context()), catalog(locale)
            )
            self.assertNotIn("report.", summary)


if __name__ == "__main__":
    unittest.main()
