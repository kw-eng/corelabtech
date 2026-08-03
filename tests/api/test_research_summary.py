import unittest

from services.research_summary import build_research_summary, valid_research_narration


class ResearchSummaryTests(unittest.TestCase):
    def test_summary_excludes_identity_and_raw_samples(self):
        summary = build_research_summary({
            "client_id": "PRIVATE",
            "features": {"samples_total": 10, "samples_synchronized": 8, "raw": ["private"]},
        })

        self.assertEqual(summary["version"], "research-summary-v1")
        self.assertNotIn("PRIVATE", str(summary["fact_sheet"]))
        self.assertNotIn("raw", str(summary["fact_sheet"]))
        self.assertEqual(summary["narration"]["source"], "deterministic_fallback")
        self.assertIn("Methods", summary["narration"]["text"])

    def test_research_fact_sheet_exposes_versions_and_rejects_unsafe_narration(self):
        summary = build_research_summary({
            "model_version": "wellness-rules-v2",
            "features": {
                "hrv_algorithm_version": "rr-clean-v2",
                "hrv_window_seconds": 60,
            },
        })

        facts = summary["fact_sheet"]
        self.assertEqual(facts["measurements"]["hrv_algorithm_version"], "rr-clean-v2")
        self.assertIn("wellness-rules-v2", summary["sections"]["methods"])
        self.assertFalse(valid_research_narration("diagnoza", facts))
