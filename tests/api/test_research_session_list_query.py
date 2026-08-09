import unittest
from pathlib import Path


class ResearchSessionListQueryTests(unittest.TestCase):
    def test_session_list_aggregates_visible_audit_exports_once(self):
        source = Path("services/session_service.py").read_text(encoding="utf-8")
        start = source.index("def list_research_sessions")
        function_source = source[start:source.index("def ", start + 4)]
        self.assertIn("report_exports AS", function_source)
        self.assertIn("JOIN listed_sessions", function_source)
        self.assertNotIn("EXISTS (", function_source)

    def test_dashboard_has_one_initial_session_list_request(self):
        source = Path("templates/research_dashboard.html").read_text(encoding="utf-8")
        self.assertEqual(source.count('fetch("/api/sessions?limit=100"'), 1)
