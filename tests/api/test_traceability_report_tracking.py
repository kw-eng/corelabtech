import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import app as app_module
import routes.research_routes as research_routes
import services.session_service as session_service
import services.traceability_service as traceability_service
from services.report_generator import ReportExport
from auth.user_model import User


class FakeCursor:
    def __init__(self, results_by_query):
        self.results_by_query = results_by_query
        self.current_result = None
        self.executed = []

    def execute(self, query, params=None):
        self.executed.append((query, params))
        normalized = " ".join(query.lower().split())

        for marker, result in self.results_by_query:
            if marker in normalized:
                self.current_result = result
                return

        self.current_result = []

    def fetchone(self):
        if isinstance(self.current_result, list):
            return self.current_result[0] if self.current_result else None

        return self.current_result

    def fetchall(self):
        if isinstance(self.current_result, list):
            return self.current_result

        return [] if self.current_result is None else [self.current_result]

    def close(self):
        pass


class FakeConnection:
    def __init__(self, results_by_query):
        self.cursor_instance = FakeCursor(results_by_query)
        self.committed = False
        self.closed = False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.committed = True

    def rollback(self):
        pass

    def close(self):
        self.closed = True


class TraceabilityReportTrackingTests(unittest.TestCase):
    def setUp(self):
        self.app = app_module.app
        self.app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=False,
            RATELIMIT_ENABLED=False,
        )
        self.app.login_manager._user_callback = lambda user_id: User(
            id=user_id,
            user_id="OPERATOR_1",
            email="operator@example.test",
            password_hash="",
            role="operator",
            is_active=True,
            organization_id=1,
            location_id=1,
        )
        self.client = self.app.test_client()

        with self.client.session_transaction() as session:
            session["_user_id"] = "1"
            session["_fresh"] = True

    def test_session_traceability_returns_pipeline_and_report_export_state(self):
        now = datetime(2026, 7, 28, 12, 0, 0)
        fake_connection = FakeConnection([
            (
                "from fit_imports where session_id",
                [
                    (
                        "hr.fit", "completed", 120, 0, now, None,
                        "chest_hrm", "Garmin HRM 600", "ecg", None, "fit",
                    )
                ],
            ),
            (
                "from csv_imports where session_id",
                [
                    (
                        "spo2.csv", "completed", 130, 1, now, None,
                        "finger_oximeter", "Checkme O2", "ppg", None,
                    )
                ],
            ),
            (
                "from merge_jobs where session_id",
                [(7, "COMPLETED", now, now, 120, 130, 118, "ok")],
            ),
            (
                "from ai_results where session_id",
                [(11, 90.0, 81.0, False, now)],
            ),
            (
                "from audit_log where session_id",
                [
                    (
                        21,
                        "OPERATOR_1",
                        "operator",
                        "report.export",
                        "session",
                        "SESSION_1",
                        "CLIENT_1",
                        "SESSION_1",
                        "success",
                        {"format": "pdf"},
                        now,
                    )
                ],
            ),
        ])

        with patch.object(
            research_routes,
            "get_research_session",
            return_value={
                "session_id": "SESSION_1",
                "user_id": "CLIENT_1",
                "client_id": "CLIENT_1",
                "created_at": now,
            },
        ), patch.object(traceability_service, "db", return_value=fake_connection):
            response = self.client.get("/api/session_traceability/SESSION_1")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["report_exported"])
        self.assertEqual(payload["client_id"], "CLIENT_1")

        steps = {step["key"]: step for step in payload["steps"]}
        self.assertEqual(steps["session_created"]["status"], "completed")
        self.assertEqual(steps["fit_imported"]["status"], "completed")
        self.assertEqual(steps["csv_imported"]["status"], "completed")
        self.assertEqual(steps["merge_completed"]["status"], "completed")
        self.assertEqual(steps["ai_generated"]["status"], "completed")
        self.assertEqual(steps["report_exported"]["status"], "completed")
        self.assertEqual(payload["events"][0]["action"], "report.export")
        self.assertEqual(payload["data_sources"][0]["import_type"], "fit")

    def test_session_report_download_records_report_export_audit_event(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_path = Path(tmp_dir) / "session.pdf"
            report_path.write_bytes(b"%PDF-1.4\n% test\n")
            audit_events = []

            with patch.object(
                research_routes,
                "generate_report_for_session",
                return_value=ReportExport(
                    path=report_path,
                    download_name="corelabtech_SESSION_1_report.pdf",
                    audit_action="report.export",
                    audit_entity_type="session",
                    audit_entity_id="SESSION_1",
                    audit_client_id="CLIENT_1",
                    audit_session_id="SESSION_1",
                    audit_details={
                        "format": "pdf",
                        "report_type": "single_session",
                        "filename": "corelabtech_SESSION_1_report.pdf",
                    },
                ),
            ), patch.object(
                research_routes,
                "write_audit_event",
                side_effect=lambda **kwargs: audit_events.append(kwargs),
            ):
                response = self.client.get("/report/SESSION_1")
                response.get_data()
                response.close()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Disposition"].count(".pdf"), 1)
        self.assertEqual(len(audit_events), 1)
        self.assertEqual(audit_events[0]["action"], "report.export")
        self.assertEqual(audit_events[0]["entity_type"], "session")
        self.assertEqual(audit_events[0]["entity_id"], "SESSION_1")
        self.assertEqual(audit_events[0]["client_id"], "CLIENT_1")
        self.assertEqual(audit_events[0]["session_id"], "SESSION_1")
        self.assertEqual(audit_events[0]["details"]["report_type"], "single_session")

    def test_series_report_download_records_series_export_audit_event(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            audit_events = []
            report_path = Path(tmp_dir) / "series.pdf"
            report_path.write_bytes(b"%PDF-1.4\n% series\n")

            with patch.object(
                research_routes,
                "generate_series_report_for_client",
                return_value=ReportExport(
                    path=report_path,
                    download_name="corelabtech_CLIENT_1_series_10_report.pdf",
                    audit_action="series_report.export",
                    audit_entity_type="client_series",
                    audit_entity_id="CLIENT_1",
                    audit_client_id="CLIENT_1",
                    audit_session_id=None,
                    audit_details={
                        "format": "pdf",
                        "report_type": "session_series",
                        "series_limit": 10,
                        "records": 2,
                        "filename": "corelabtech_CLIENT_1_series_10_report.pdf",
                    },
                ),
            ), patch.object(
                research_routes,
                "write_audit_event",
                side_effect=lambda **kwargs: audit_events.append(kwargs),
            ):
                response = self.client.get("/report/series/CLIENT_1?limit=10")
                response.get_data()
                response.close()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(audit_events), 1)
        self.assertEqual(audit_events[0]["action"], "series_report.export")
        self.assertEqual(audit_events[0]["entity_type"], "client_series")
        self.assertEqual(audit_events[0]["entity_id"], "CLIENT_1")
        self.assertEqual(audit_events[0]["client_id"], "CLIENT_1")
        self.assertEqual(audit_events[0]["details"]["report_type"], "session_series")
        self.assertEqual(audit_events[0]["details"]["series_limit"], 10)

    def test_list_research_sessions_exposes_report_export_flags(self):
        exported_at = datetime(2026, 7, 28, 12, 30, 0)
        fake_connection = FakeConnection([
            (
                "from full_sessions fs left join protocols",
                [
                    (
                        "SESSION_1",
                        "CLIENT_1",
                        "completed",
                        True,
                        exported_at,
                        "Wellness 1.5 ATA",
                        1.5,
                        3,
                        True,
                        exported_at,
                    )
                ],
            )
        ])

        with patch.object(session_service, "db", return_value=fake_connection):
            rows = session_service.list_research_sessions(
                requesting_user_id="OPERATOR_1",
                requesting_role="operator",
                requesting_organization_id=1,
            )

        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["report_exported"])
        self.assertEqual(rows[0]["report_exported_at"], exported_at.isoformat())
        self.assertEqual(rows[0]["client_session_number"], 3)


if __name__ == "__main__":
    unittest.main()
