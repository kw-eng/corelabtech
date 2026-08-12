"""Focused regression coverage for commercial IP and browser exposure boundaries."""

import os
from pathlib import Path
import unittest

from flask import Flask

from security.headers import configure_security_headers
from services.generated_media_service import generated_media_presentation
from services.prompt_builder_service import build_generation_prompt


ROOT = Path(__file__).resolve().parents[2]


class CommercialSecurityBoundaryTests(unittest.TestCase):
    def test_generated_media_browser_projection_excludes_private_metadata(self):
        item = {
            "id": 9, "media_type": "image", "file_name": "asset.svg",
            "prompt": "private provider instruction", "negative_prompt": "private negative instruction",
            "file_path": "assets/private.svg", "notes": "private review note", "created_by": 42,
        }
        projection = generated_media_presentation(item)
        self.assertEqual(projection["id"], 9)
        self.assertEqual(projection["file_name"], "asset.svg")
        for private_key in ("prompt", "negative_prompt", "file_path", "notes", "created_by"):
            self.assertNotIn(private_key, projection)

    def test_generation_prompt_is_server_owned_and_contains_brand_constraints(self):
        prompt = build_generation_prompt(
            character_id="athlete", scene_id="wellness", output_type="image"
        )
        self.assertIn("CoreLabTech AI Content Studio", prompt)
        self.assertIn("Do not include commercial logos", prompt)
        browser_source = (ROOT / "static/js/content_studio/generate.js").read_text(encoding="utf-8")
        self.assertNotIn("Use the official CoreLabTech character reference", browser_source)
        self.assertIn("protected on the CoreLabTech server", browser_source)

    def test_content_studio_routes_use_safe_projection_and_server_authorization(self):
        source = (ROOT / "routes/content_studio_routes.py").read_text(encoding="utf-8")
        self.assertIn("generated_media_presentation", source)
        self.assertIn("Direct media registration is restricted to administrators.", source)
        self.assertIn("Only administrators can approve, publish, or finalize media.", source)
        self.assertIn("prompt=build_generation_prompt(", source)

    def test_security_headers_include_policy_boundaries_and_production_hsts(self):
        previous = os.environ.get("APP_ENV")
        os.environ["APP_ENV"] = "production"
        try:
            app = Flask(__name__)
            configure_security_headers(app)

            @app.get("/")
            def home():
                return "ok"

            response = app.test_client().get("/")
        finally:
            if previous is None:
                os.environ.pop("APP_ENV", None)
            else:
                os.environ["APP_ENV"] = previous

        csp = response.headers["Content-Security-Policy"]
        self.assertIn("frame-ancestors 'self'", csp)
        self.assertIn("base-uri 'self'", csp)
        self.assertEqual(response.headers["Permissions-Policy"], "camera=(), microphone=(), geolocation=(), payment=(), usb=()")
        self.assertIn("max-age=31536000", response.headers["Strict-Transport-Security"])

    def test_research_500_errors_are_not_reflected_to_the_browser(self):
        source = (ROOT / "routes/research_routes.py").read_text(encoding="utf-8")
        self.assertEqual(source.count('message = "An internal server error occurred."'), 2)

    def test_admin_account_mutations_use_normal_csrf_protection(self):
        routes = (ROOT / "routes/research_routes.py").read_text(encoding="utf-8")
        script = (ROOT / "static/js/admin_accounts.js").read_text(encoding="utf-8")
        self.assertNotIn('@csrf.exempt\n@research_bp.route("/api/admin/accounts", methods=["POST"])', routes)
        self.assertNotIn('@csrf.exempt\n@research_bp.route("/api/admin/accounts/reset_password", methods=["POST"])', routes)
        self.assertIn("authenticatedJsonHeaders", script)
        self.assertIn('"X-CSRFToken": csrfToken', script)
