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
