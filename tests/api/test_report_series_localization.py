import json
import unittest
from pathlib import Path


class SeriesReportLocalizationTests(unittest.TestCase):
    def test_polish_catalog_localizes_report_terms_and_findings(self):
        catalog = json.loads(Path("translations/pl.json").read_text(encoding="utf-8"))
        self.assertEqual(catalog["report.label_client"], "Klient")
        self.assertEqual(catalog["report.evidence_preliminary"], "Wstępny")
        self.assertIn("dostępnych", catalog["report.finding_evidence"].lower())
        self.assertIn("Pierwsza dostępna", catalog["report.comparison_first_latest"])

    def test_english_catalog_keeps_english_comparison(self):
        catalog = json.loads(Path("translations/en.json").read_text(encoding="utf-8"))
        self.assertIn("First {count}", catalog["report.comparison_first_last"])

    def test_single_session_report_catalog_has_localized_quality_and_research_labels(self):
        pl = json.loads(Path("translations/pl.json").read_text(encoding="utf-8"))
        en = json.loads(Path("translations/en.json").read_text(encoding="utf-8"))
        for key in (
            "report.label_data_quality_score",
            "report.quality_alignment_review",
            "report.research_methods_versions",
            "report.research_content_abstract",
            "report.status_completed",
        ):
            self.assertIn(key, pl)
            self.assertIn(key, en)
        self.assertEqual(pl["report.table_recovery"], "REGENERACJA")
