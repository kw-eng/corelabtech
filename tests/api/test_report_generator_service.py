import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import services.report_generator as report_generator
from services.session_service import build_series_pdf_report


class ReportGeneratorServiceTests(unittest.TestCase):
    def test_generate_report_for_session_returns_export_metadata(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_path = Path(tmp_dir) / "session.pdf"
            report_path.write_bytes(b"%PDF-1.4\n% session\n")

            with patch.object(
                report_generator,
                "generate_session_report",
                return_value=report_path,
            ) as generate_session_report, patch.object(
                report_generator,
                "get_research_session",
                return_value={
                    "session_id": "SESSION_1",
                    "client_id": "CLIENT_1",
                },
            ):
                export = report_generator.generate_report_for_session(
                    session_id="SESSION_1",
                    requesting_user_id="OPERATOR_1",
                    requesting_role="operator",
                    requesting_organization_id=1,
                    locale="pl",
                )

        generate_session_report.assert_called_once()
        self.assertEqual(
            generate_session_report.call_args.kwargs["locale"],
            "pl",
        )
        self.assertEqual(export.path, report_path)
        self.assertEqual(export.download_name, "corelabtech_session_SESSION_1_PL.pdf")
        self.assertEqual(export.audit_action, "report.export")
        self.assertEqual(export.audit_entity_type, "session")
        self.assertEqual(export.audit_entity_id, "SESSION_1")
        self.assertEqual(export.audit_client_id, "CLIENT_1")
        self.assertEqual(export.audit_session_id, "SESSION_1")
        self.assertEqual(export.audit_details["report_type"], "single_session")

    def test_generate_series_report_for_client_returns_export_metadata(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            reports_dir = Path(tmp_dir)
            created_paths = []
            received_locales = []

            def fake_build_series_pdf_report(*, path, series_data, locale=None):
                created_paths.append(Path(path))
                received_locales.append(locale)
                Path(path).write_bytes(b"%PDF-1.4\n% series\n")

            with patch.object(
                report_generator,
                "REPORTS_DIRECTORY",
                reports_dir,
            ), patch.object(
                report_generator,
                "can_access_client_record",
                return_value=True,
            ), patch.object(
                report_generator,
                "get_user_series_trends",
                return_value={
                    "status": "ok",
                    "user_id": "CLIENT_1",
                    "records": 3,
                    "analyses": [],
                },
            ), patch.object(
                report_generator,
                "build_series_pdf_report",
                side_effect=fake_build_series_pdf_report,
            ):
                export = report_generator.generate_series_report_for_client(
                    user_id="CLIENT_1",
                    requesting_user_id="OPERATOR_1",
                    requesting_role="operator",
                    requesting_organization_id=1,
                    trend_limit=10,
                    locale="pl",
                )

        self.assertEqual(len(created_paths), 1)
        self.assertEqual(received_locales, ["pl"])
        self.assertEqual(export.path, created_paths[0])
        self.assertEqual(
            export.download_name,
            "corelabtech_series_CLIENT_1_last-10_PL.pdf",
        )
        self.assertEqual(export.audit_action, "series_report.export")
        self.assertEqual(export.audit_entity_type, "client_series")
        self.assertEqual(export.audit_entity_id, "CLIENT_1")
        self.assertEqual(export.audit_client_id, "CLIENT_1")
        self.assertIsNone(export.audit_session_id)
        self.assertEqual(export.audit_details["series_limit"], 10)
        self.assertEqual(export.audit_details["records"], 3)

    def test_generate_series_report_for_client_rejects_forbidden_client(self):
        with patch.object(
            report_generator,
            "can_access_client_record",
            return_value=False,
        ):
            with self.assertRaises(PermissionError):
                report_generator.generate_series_report_for_client(
                    user_id="CLIENT_1",
                    requesting_user_id="OTHER_USER",
                    requesting_role="viewer",
                    requesting_organization_id=1,
                    trend_limit=10,
                )

    def test_report_download_names_are_safe_and_include_type_identity_and_locale(self):
        self.assertEqual(
            report_generator.report_download_name(
                report_type="session", identifier="S/1", locale="en"
            ),
            "corelabtech_session_S_1_EN.pdf",
        )
        self.assertEqual(
            report_generator.report_download_name(
                report_type="series", identifier="CLIENT 1", range_limit=25, locale="pl"
            ),
            "corelabtech_series_CLIENT_1_last-25_PL.pdf",
        )

    def test_series_pdf_report_renders_with_polish_locale(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "series_pl.pdf"

            build_series_pdf_report(
                path=path,
                locale="pl",
                series_data={
                    "user_id": "CLIENT_1",
                    "series_limit": 10,
                    "records": 1,
                    "session_count": 1,
                    "avg_score": 90,
                    "avg_data_quality": 81,
                    "avg_coverage": 91,
                    "avg_match_rate": 90,
                    "latest_score": 90,
                    "trend_direction": "stable",
                    "wellness_interpretation": (
                        "Trend wellness stabilny. Wymagana ocena operatora."
                    ),
                    "first_last_comparison": {
                        "first_avg_score": 90,
                        "last_avg_score": 91,
                        "score_delta": 1,
                        "first_avg_data_quality": 80,
                        "last_avg_data_quality": 82,
                        "data_quality_delta": 2,
                    },
                    "data_quality_engine": {
                        "total_missing_samples": 0,
                        "sensor_gap_sessions": 0,
                        "hr_pulse_mismatch_sessions": 0,
                        "spo2_warning_sessions": 0,
                        "warning_counts": {},
                        "explanation": (
                            "Jakość danych opisuje zaufanie do synchronizacji."
                        ),
                    },
                    "analyses": [
                        {
                            "session_id": "SESSION_1",
                            "created_at": "2026-07-29T08:00:00",
                            "overall_score": 90,
                            "data_quality_score": 81,
                            "match_rate": 90,
                            "avg_spo2": 98,
                            "avg_pulse": 58,
                            "session_flagged": False,
                            "quality_warning_count": 0,
                        }
                    ],
                },
            )

            self.assertTrue(path.exists())
            self.assertGreater(path.stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
