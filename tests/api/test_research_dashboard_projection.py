import unittest

from services.research_dashboard_projection import (
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
