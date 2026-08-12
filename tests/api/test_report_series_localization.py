import json
import unittest
from pathlib import Path

from services.session_service import (
    localized_count,
    localized_series_trend,
    localized_session_findings,
    localized_warning_list,
)


class SeriesReportLocalizationTests(unittest.TestCase):
    def test_polish_catalog_localizes_report_terms_and_findings(self):
        catalog = json.loads(Path("translations/pl.json").read_text(encoding="utf-8"))
        self.assertEqual(catalog["report.label_client"], "Klient")
        self.assertEqual(catalog["report.evidence_preliminary"], "Wstępny")
        self.assertIn("{sessions}", catalog["report.finding_evidence"])
        self.assertIn("dowod", catalog["report.finding_evidence"].lower())
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

    def test_single_session_catalog_has_localized_context_and_baseline_status(self):
        pl = json.loads(Path("translations/pl.json").read_text(encoding="utf-8"))
        en = json.loads(Path("translations/en.json").read_text(encoding="utf-8"))
        for catalog in (pl, en):
            for key in (
                "report.wellness_status_baseline",
                "report.context_pulse_hr",
                "report.context_sleep_hours",
                "report.context_energy_level",
                "report.context_value_fair",
                "report.context_value_recovery",
            ):
                self.assertIn(key, catalog)
                self.assertFalse(catalog[key].startswith("report."))
        self.assertEqual(pl["report.context_pulse_hr"], "Puls / HR")
        self.assertEqual(pl["report.context_value_recovery"], "Regeneracja")

    def test_report_builder_localizes_baseline_and_context_values(self):
        source = Path("services/session_service.py").read_text(encoding="utf-8")
        self.assertIn('"report.wellness_status",', source)
        self.assertIn('localized_report_enum(catalog, "report.context_value", item)', source)
        self.assertIn('report_text(catalog, f"report.context_{key}")', source)

    def test_report_builder_uses_localized_deterministic_text_not_stored_narration(self):
        source = Path("services/session_service.py").read_text(encoding="utf-8")
        self.assertIn("localized_session_interpretation(", source)
        self.assertIn("localized_operator_review(", source)
        self.assertIn("localized_warning_names(catalog, warnings)", source)
        self.assertNotIn('escape_text(analysis.get("summary"))', source)

    def test_single_session_pdf_uses_shared_response_presentation_model(self):
        source = Path("services/session_service.py").read_text(encoding="utf-8")
        self.assertIn("build_localized_session_response", source)
        self.assertIn("response_report_flowables", source)

    def test_report_warning_codes_are_localized_without_leaking_i18n_keys(self):
        warning_codes = [
            "missing_hrv_or_rr",
            "time_alignment_uncertain",
            "heart_rate_source_unknown",
            "insufficient_rr_for_hrv",
            "unapproved_rr_source",
        ]
        for locale in ("en", "pl"):
            catalog = json.loads(
                Path(f"translations/{locale}.json").read_text(encoding="utf-8")
            )
            localized = localized_warning_list(catalog, warning_codes)
            self.assertNotIn("report.warning_", localized)
            self.assertNotIn("missing_hrv_or_rr", localized)

    def test_customer_report_catalog_has_premium_presentation_terms_in_both_locales(self):
        for locale in ("en", "pl"):
            catalog = json.loads(Path(f"translations/{locale}.json").read_text(encoding="utf-8"))
            for key in (
                "report.response_not_recorded",
                "report.program_progress",
                "report.technical_appendix",
                "report.longitudinal_view",
                "report.trend_score_chart",
            ):
                self.assertIn(key, catalog)
                self.assertFalse(catalog[key].startswith("report."))

    def test_customer_findings_use_localized_response_facts_without_warning_codes(self):
        catalog = json.loads(Path("translations/pl.json").read_text(encoding="utf-8"))
        findings = localized_session_findings(
            catalog,
            {"overall_score": 80, "data_quality_score": 90, "result": {"wellness_status": "stable"}},
            {"observations": ["Dostepny pomiar jest stabilny."], "limitations": ["Zgodnosc sensorow wymaga weryfikacji."]},
        )
        rendered = " ".join(findings)
        self.assertIn("stabil", rendered.lower())
        self.assertNotIn("sensor_alignment_warning", rendered)
        self.assertNotIn("report.", rendered)

    def test_polish_report_count_forms_are_customer_grammatical(self):
        catalog = json.loads(Path("translations/pl.json").read_text(encoding="utf-8"))
        self.assertEqual(localized_count(catalog, 1, "session"), "1 sesja")
        self.assertEqual(localized_count(catalog, 2, "session"), "2 sesje")
        self.assertEqual(localized_count(catalog, 5, "session"), "5 sesji")
        self.assertEqual(localized_count(catalog, 1, "warning"), "1 ostrzeżenie")
        self.assertEqual(localized_count(catalog, 2, "warning"), "2 ostrzeżenia")
        self.assertEqual(localized_count(catalog, 5, "warning"), "5 ostrzeżeń")

    def test_dashboard_exposes_symmetric_persistent_workflow_state(self):
        source = Path("templates/research_dashboard.html").read_text(encoding="utf-8")
        self.assertIn('id="sessionWorkflowState"', source)
        self.assertIn('id="seriesWorkflowState"', source)
        self.assertIn("workflowState.session.analyzed = true", source)
        self.assertIn("workflowState.series.analyzed = true", source)
        self.assertIn("workflow.reported = true", source)
        self.assertIn("workflow_session_loaded", source)
        self.assertIn("workflow_analysis_completed", source)
        self.assertIn("workflow_series_loaded", source)
        self.assertIn("workflow_trend_completed", source)
        self.assertIn('row.textContent = `${complete ? "✓" : "○"}', source)

    def test_dashboard_forwards_active_locale_to_both_report_downloads(self):
        source = Path("templates/research_dashboard.html").read_text(encoding="utf-8")
        self.assertGreaterEqual(source.count("window.CORELABTECH_LOCALE"), 3)
        self.assertIn("function localizedTrend(value)", source)
        self.assertIn("localizedTrend(data.trend_direction)", source)

    def test_dashboard_uses_accessible_localized_operation_feedback(self):
        source = Path("templates/research_dashboard.html").read_text(encoding="utf-8")
        self.assertIn('id="missionNotice"', source)
        self.assertIn('role="status"', source)
        self.assertIn('aria-live="polite"', source)
        for key in (
            "mission.session_loaded",
            "mission.session_report_generated",
            "mission.series_loaded",
            "mission.series_report_generated",
        ):
            self.assertIn(key, source)

    def test_dashboard_uses_locale_safe_recovery_and_research_summary_requests(self):
        source = Path("templates/research_dashboard.html").read_text(encoding="utf-8")
        self.assertIn("mission.recovery_summary_complete", source)
        self.assertIn("mission.recovery_summary_recorded", source)
        self.assertIn("research-summary?lang=${locale}", source)

    def test_series_trend_never_exposes_an_internal_translation_key(self):
        pl = json.loads(Path("translations/pl.json").read_text(encoding="utf-8"))
        en = json.loads(Path("translations/en.json").read_text(encoding="utf-8"))
        self.assertEqual(localized_series_trend(pl, "unknown"), pl["report.trend_unknown"])
        self.assertEqual(localized_series_trend(en, "unexpected_state"), "Unknown")
        self.assertNotIn("report.trend_", localized_series_trend(pl, "unexpected_state"))

    def test_workflow_phase_mapping_is_localized_without_changing_step_ids(self):
        template = Path("templates/chamber_testing.html").read_text(encoding="utf-8")
        en = json.loads(Path("translations/en.json").read_text(encoding="utf-8"))
        pl = json.loads(Path("translations/pl.json").read_text(encoding="utf-8"))
        self.assertIn('id="step_pre"', template)
        self.assertIn('id="step_during"', template)
        self.assertIn('id="step_post"', template)
        self.assertIn('class="analysis-phase">PRE', template)
        self.assertEqual(
            en["chamber.phase_mapping_note"],
            "Operator workflow mapped to physiological analysis phases.",
        )
        self.assertEqual(
            pl["chamber.phase_mapping_note"],
            "Etapy pracy operatora odpowiadają fazom analizy fizjologicznej.",
        )
