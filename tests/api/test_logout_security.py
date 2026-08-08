"""Regression checks for the browser logout security contract.

These tests intentionally inspect the route/template contract without needing
PostgreSQL, so they remain useful during local development and CI setup.
"""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class LogoutSecurityContractTests(unittest.TestCase):
    def test_logout_accepts_post_only(self):
        source = (ROOT / "auth" / "auth_routes.py").read_text(encoding="utf-8")
        self.assertIn('@auth_bp.route("/logout", methods=["POST"])', source)

    def test_logout_forms_include_csrf_token(self):
        for relative_path in ("templates/layout.html", "templates/profile.html"):
            source = (ROOT / relative_path).read_text(encoding="utf-8")
            self.assertIn('action="{{ url_for(\'auth.logout\') }}" method="post"', source)
            self.assertIn('name="csrf_token" value="{{ csrf_token() }}"', source)

    def test_layout_declares_responsive_viewport(self):
        source = (ROOT / "templates" / "layout.html").read_text(encoding="utf-8")
        self.assertIn('name="viewport" content="width=device-width, initial-scale=1"', source)

    def test_session_cookie_policy_is_explicit(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn('app.config["SESSION_COOKIE_SAMESITE"]', source)
        self.assertIn('app.config["REMEMBER_COOKIE_SAMESITE"]', source)

    def test_login_marks_the_session_permanent(self):
        source = (ROOT / "auth" / "auth_routes.py").read_text(encoding="utf-8")
        self.assertIn("session.permanent = True", source)


if __name__ == "__main__":
    unittest.main()
