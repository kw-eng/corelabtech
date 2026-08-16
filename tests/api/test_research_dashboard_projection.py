import unittest
import json
from pathlib import Path

from services.research_dashboard_projection import (
    build_analysis_presentation,
    build_research_dashboard_projection,
)


def result_with_timeline(count=3):
    timeline = [
        {
            "timestamp": f"2026-01-01T00:{index:02d}:00Z",
            "heart_rate": 60 + index,
            "heart_rate_bpm": 60 + index,
            "pulse": 59 + index,
            "pulse_rate_bpm": 59 + index,
            "spo2": 98,
            "hrv": {"raw_rr": [800, 810]},
            "rr_interval": [800, 810],
            "synchronized": True,
            "hr_source_type": "chest_hrm",
        }
        for index in range(count)
    ]
    return {
        "ai_result_id": 9,
        "merge_id": 7,
        "session_id": "SESSION_1",
        "overall_score": 91,
        "data_quality_score": 82,
        "anomaly_detected": False,
        "features": {"unused_large_field": list(range(100))},
        "result": {
            "overall_score": 91,
            "data_quality_score": 82,
            "analysis_confidence": "moderate",
            "anomaly_detected": False,
            "quality_warnings": ["sensor_alignment_warning"],
            "summary": "Stable wellness response.",
            "features": {
                "avg_spo2": 98,
                "avg_pulse": 60,
                "avg_hrv": 45,
                "hrv_windows": list(range(100)),
            },
            "timeline": timeline,
            "session_summary": {"content": "summary"},
            "session_comparison": {"available": False},
            "recovery_coach": {"status": "available"},
            "reasons": ["quality note"],
            "positive_findings": ["stable"],
            "wellness_disclaimer": "Wellness only.",
            "medical_disclaimer": "Wellness only.",
            "narration": {"fact_sheet": {"large_internal": list(range(100))}},
        },
    }


class ResearchDashboardProjectionTests(unittest.TestCase):
    def test_legacy_analysis_presentation_keeps_required_fields_without_internal_payloads(self):
        projection = build_analysis_presentation(result_with_timeline(), timeline_sample=2)

        self.assertEqual(projection["overall_score"], 91)
        self.assertEqual(projection["features"]["avg_spo2"], 98)
        self.assertEqual(len(projection["timeline"]), 2)
        self.assertEqual(projection["result"]["session_summary"]["content"], "summary")
        self.assertNotIn("narration", projection)
        self.assertNotIn("model_name", projection)
        self.assertNotIn("user_id", projection)
        self.assertNotIn("hrv_windows", projection["features"])
        self.assertNotIn("rr_interval", projection["timeline"][0])
        self.assertNotIn("raw_rr", str(projection))

    def test_timeline_sample_contract_limits_dashboard_timeline(self):
        result = result_with_timeline(1_000)
        projection = build_research_dashboard_projection(result, timeline_sample=700)

        self.assertEqual(projection["timeline_total"], 1_000)
        self.assertEqual(projection["timeline_sampled"], 700)
        self.assertEqual(len(projection["timeline"]), 700)
        self.assertEqual(projection["timeline"][0]["timestamp"], "2026-01-01T00:00:00Z")
        self.assertEqual(projection["timeline"][-1]["timestamp"], "2026-01-01T00:999:00Z")

    def test_projection_keeps_dashboard_data_without_raw_telemetry(self):
        projection = build_research_dashboard_projection(
            result_with_timeline(), timeline_sample=700
        )

        self.assertEqual(projection["overall_score"], 91)
        self.assertEqual(projection["data_quality_score"], 82)
        self.assertEqual(projection["features"]["avg_hrv"], 45)
        self.assertEqual(projection["timeline"][0]["hrv"], None)
        self.assertNotIn("rr_interval", projection["timeline"][0])
        self.assertNotIn("hr_source_type", projection["timeline"][0])
        self.assertNotIn("narration", projection)
        self.assertNotIn("hrv_windows", projection["features"])

    def test_projection_does_not_change_persisted_analysis(self):
        result = result_with_timeline()
        original_timeline = list(result["result"]["timeline"])
        build_research_dashboard_projection(result, timeline_sample=2)
        self.assertEqual(result["result"]["timeline"], original_timeline)

    def test_projection_rebuilds_locale_specific_summary_from_context(self):
        result = result_with_timeline()
        result["result"].update({
            "wellness_status": "baseline",
            "session_summary": {"content": "Ograniczenia danych\nStale Polish text"},
        })
        result["result"]["features"]["session_context"] = {
            "pre_check_in": {"spo2": 97, "pulse": 70},
            "post_check_out": {"spo2": 98, "pulse": 68},
        }
        catalog = json.loads(Path("translations/en.json").read_text(encoding="utf-8"))

        projection = build_research_dashboard_projection(
            result, timeline_sample=2, catalog=catalog
        )

        self.assertIn("Data limitations", projection["session_summary"]["content"])
        self.assertIn("Check-in\nSpO2: 97%; Pulse / HR: 70 bpm", projection["session_summary"]["content"])
        self.assertNotIn("Stale Polish text", projection["session_summary"]["content"])
        self.assertEqual(
            projection["session_response_presentation"]["completeness"],
            "0 of 3 objective comparisons available",
        )
        self.assertNotIn("raw_rr", str(projection["session_response"]))

    def test_projection_response_presentation_remains_small_and_localized(self):
        result = result_with_timeline()
        result["result"]["session_response"] = {
            "pre": {"spo2": 97},
            "during": {},
            "post": {"spo2": 98},
            "deltas": {"spo2_percentage_points": 1, "heart_rate_bpm": None, "hrv_rmssd_ms": None},
            "availability": {"available_delta_count": 1, "possible_delta_count": 3},
            "confidence": "medium",
            "subjective_context": {"post": {}},
            "limitations": [],
        }
        catalog = json.loads(Path("translations/en.json").read_text(encoding="utf-8"))

        projection = build_research_dashboard_projection(
            result, timeline_sample=2, catalog=catalog
        )

        self.assertEqual(projection["session_response_presentation"]["confidence"], "Insufficient")
        self.assertEqual(
            projection["session_response_presentation"]["pre_label"],
            "Check-in snapshot",
        )
        self.assertEqual(projection["customer_insight"]["status"], "Available session insight")
        self.assertEqual(len(projection["timeline"]), 2)

    def test_polish_projection_uses_catalog_not_persisted_disclaimer_or_codes(self):
        result = result_with_timeline()
        result["result"].update({
            "wellness_status": "data_quality_warning",
            "quality_warnings": ["missing_hrv_or_rr", "unknown_future_code"],
            "wellness_disclaimer": "Wellness and educational insight only.",
            "medical_disclaimer": "Wellness and educational insight only.",
        })
        catalog = json.loads(Path("translations/pl.json").read_text(encoding="utf-8"))

        projection = build_research_dashboard_projection(
            result, timeline_sample=2, catalog=catalog
        )

        summary = projection["session_summary"]
        self.assertEqual(summary["disclaimer"], catalog["mission.wellness_disclaimer"])
        self.assertNotIn("Wellness and educational insight", summary["content"])
        self.assertIn(catalog["report.warning_missing_hrv_or_rr"], summary["content"])
        self.assertIn(catalog["report.warning_unclassified"], summary["content"])
        self.assertIn(catalog["report.wellness_status_data_quality_warning"], summary["content"])
        self.assertNotIn("missing_hrv_or_rr", summary["content"])
        self.assertNotIn("unknown_future_code", summary["content"])
        self.assertNotIn("wellness_disclaimer", projection)
        self.assertNotIn("medical_disclaimer", projection)

    def test_dashboard_template_separates_raw_diagnostics_from_normal_ui(self):
        source = Path("templates/research_dashboard.html").read_text(encoding="utf-8")

        self.assertIn('{% if current_user.role == "admin" %}', source)
        self.assertIn("mission.technical_diagnostics", source)
        self.assertIn("mission.technical_details", source)
        self.assertIn("translateDiagnosticCode", source)
