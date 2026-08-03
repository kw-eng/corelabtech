import unittest

from services.insight_views import (
    build_operator_report,
    build_recovery_coach,
    build_session_comparison,
    build_session_summary,
    session_quality_label,
)


class InsightViewTests(unittest.TestCase):
    def test_operator_report_requests_review_for_low_quality_data(self):
        report = build_operator_report(
            {
                "data_quality_score": 45,
                "quality_warnings": ["low_match_rate"],
                "features": {
                    "match_rate": 45,
                    "signal_quality": "low",
                    "time_alignment_quality": "low",
                    "session_context": {"execution_status": "completed"},
                },
            }
        )

        self.assertTrue(report["technical_attention_required"])
        self.assertEqual(report["operator_action"], "review_required")

    def test_session_comparison_uses_only_personal_history(self):
        history = {
            "recent_sessions": [
                {"rmssd": 50, "avg_hr": 60, "avg_spo2": 98, "data_quality_score": 90},
                {"rmssd": 40, "avg_hr": 64, "avg_spo2": 97, "data_quality_score": 80},
                {"rmssd": 45, "avg_hr": 62, "avg_spo2": 98, "data_quality_score": 85},
            ]
        }

        comparison = build_session_comparison(history)

        self.assertEqual(comparison["available_sessions"], 3)
        self.assertEqual(comparison["confidence"], "low")
        self.assertEqual(
            comparison["comparisons"]["1"]["metrics"]["rmssd"]["percent_change"],
            25.0,
        )

    def test_session_comparison_excludes_low_quality_reference_data(self):
        comparison = build_session_comparison(
            {
                "recent_sessions": [
                    {"rmssd": 50, "data_quality_score": 90},
                    {"rmssd": 40, "data_quality_score": 55},
                ]
            }
        )

        window = comparison["comparisons"]["1"]
        self.assertFalse(window["available"])
        self.assertEqual(window["excluded_reference_sessions"], 1)
        self.assertEqual(window["reason"], "no_eligible_reference_sessions")

    def test_session_comparison_requires_quality_for_latest_session(self):
        comparison = build_session_comparison(
            {
                "recent_sessions": [
                    {"rmssd": 50, "data_quality_score": 55},
                    {"rmssd": 40, "data_quality_score": 90},
                ]
            }
        )

        window = comparison["comparisons"]["1"]
        self.assertFalse(window["available"])
        self.assertEqual(
            window["reason"],
            "latest_session_data_quality_below_threshold",
        )

    def test_session_summary_exposes_narration_provenance(self):
        summary = build_session_summary(
            analysis={
                "analysis_confidence": "high",
                "data_quality_score": 92,
                "quality_warnings": [],
                "wellness_disclaimer": "Wellness only.",
            },
            narration={
                "status": "generated",
                "text": "Podsumowanie faktow.",
                "provider": "openai",
                "model": "gpt-5-mini",
                "narration_version": "llm-narration-v2",
                "fact_sheet_version": "wellness-fact-sheet-v2",
            },
        )

        self.assertEqual(summary["version"], "session-summary-v1")
        self.assertEqual(summary["source"], "llm")
        self.assertEqual(summary["content"], "Podsumowanie faktow.")

    def test_recovery_coach_requires_follow_up_before_interpretation(self):
        pending = build_recovery_coach(analysis={})
        recorded = build_recovery_coach(
            analysis={"data_quality_score": 90, "quality_warnings": []},
            follow_ups={
                "one_hour": {
                    "follow_up_window": "one_hour",
                    "energy_level": "higher",
                    "heart_rate_bpm": 61,
                    "spo2": 98,
                },
                "next_day": {"follow_up_window": "next_day", "fatigue_level": "lower"},
            },
            check_in={"pulse": 64, "spo2": 97},
            personal_history=[
                {"session_id": "a", "follow_up_window": "one_hour", "heart_rate_bpm": 62, "spo2": 98},
                {"session_id": "b", "follow_up_window": "one_hour", "heart_rate_bpm": 63, "spo2": 97},
                {"session_id": "c", "follow_up_window": "one_hour", "heart_rate_bpm": 64, "spo2": 98},
            ],
        )

        self.assertEqual(pending["status"], "follow_up_pending")
        self.assertEqual(recorded["version"], "recovery-coach-v2")
        self.assertEqual(recorded["status"], "follow_up_complete")
        self.assertEqual(recorded["follow_ups"]["next_day"]["fatigue_level"], "lower")
        self.assertEqual(
            recorded["comparisons"]["one_hour"]["metrics"]["heart_rate_bpm"]["check_in_delta"],
            -3.0,
        )
        self.assertTrue(recorded["comparisons"]["one_hour"]["history_available"])
        self.assertEqual(
            recorded["comparisons"]["one_hour"]["metrics"]["heart_rate_bpm"]["personal_history"]["delta"],
            -2.0,
        )

    def test_session_quality_is_deterministic(self):
        self.assertEqual(session_quality_label(90), "Excellent")
        self.assertEqual(session_quality_label(72), "Good")
        self.assertEqual(session_quality_label(62), "Fair")
        self.assertEqual(session_quality_label(40), "Needs review")


if __name__ == "__main__":
    unittest.main()
