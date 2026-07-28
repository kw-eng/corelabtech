import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import services.report_generator as report_generator


class ReportGeneratorServiceTests(unittest.TestCase):
    def test_generate_report_for_session_returns_export_metadata(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_path = Path(tmp_dir) / "session.pdf"
            report_path.write_bytes(b"%PDF-1.4\n% session\n")

            with patch.object(
                report_generator,
                "generate_session_report",
                return_value=report_path,
            ), patch.object(
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
                )

        self.assertEqual(export.path, report_path)
        self.assertEqual(export.download_name, "corelabtech_SESSION_1_report.pdf")
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

            def fake_build_series_pdf_report(*, path, series_data):
                created_paths.append(Path(path))
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
                )

        self.assertEqual(len(created_paths), 1)
        self.assertEqual(export.path, created_paths[0])
        self.assertEqual(
            export.download_name,
            "corelabtech_CLIENT_1_series_10_report.pdf",
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


if __name__ == "__main__":
    unittest.main()
