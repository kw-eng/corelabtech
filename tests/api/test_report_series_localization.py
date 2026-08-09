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

    def test_polish_catalog_translates_manual_validation_values(self):
        pl = json.loads(Path("translations/pl.json").read_text(encoding="utf-8"))
        self.assertEqual(
            pl["report.warning_sensor_alignment_warning"],
            "Ostrzeżenie dotyczące zgodności sensorów",
        )
        self.assertEqual(pl["report.status_as_planned"], "Ukończona zgodnie z planem")
        self.assertEqual(pl["report.phase_compression"], "Kompresja")
        self.assertEqual(pl["report.confidence_medium"], "Średnia")

    def test_report_builder_uses_localized_deterministic_text_not_stored_narration(self):
        source = Path("services/session_service.py").read_text(encoding="utf-8")
        self.assertIn("localized_session_interpretation(", source)
        self.assertIn("localized_operator_review(", source)
        self.assertIn("localized_warning_names(catalog, warnings)", source)
        self.assertNotIn('escape_text(analysis.get("summary"))', source)

    def test_dashboard_forwards_active_locale_to_both_report_downloads(self):
        source = Path("templates/research_dashboard.html").read_text(encoding="utf-8")
        self.assertEqual(source.count("window.CORELABTECH_LOCALE"), 2)
