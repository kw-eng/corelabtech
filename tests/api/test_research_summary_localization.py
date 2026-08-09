import json
import unittest
from pathlib import Path


class ResearchSummaryLocalizationTests(unittest.TestCase):
    def test_polish_report_summary_uses_polish_deterministic_content(self):
        catalog = json.loads(Path("translations/pl.json").read_text(encoding="utf-8"))
        self.assertIn("zsynchronizowanych danych", catalog["report.research_content_abstract"])
        self.assertIn("nie stanowi diagnozy", catalog["report.research_content_disclaimer"])

    def test_english_report_summary_uses_english_deterministic_content(self):
        catalog = json.loads(Path("translations/en.json").read_text(encoding="utf-8"))
        self.assertIn("Observational description", catalog["report.research_content_abstract"])
        self.assertIn("not a medical diagnosis", catalog["report.research_content_disclaimer"])
