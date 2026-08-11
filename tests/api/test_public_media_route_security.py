import unittest
from pathlib import Path
from unittest.mock import patch

import app as app_module


class PublicMediaRouteSecurityTests(unittest.TestCase):
    def setUp(self):
        self.app = app_module.app
        self.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False)
        self.client = self.app.test_client()

    def test_public_media_blueprint_has_no_mutation_route(self):
        rules = [
            rule for rule in self.app.url_map.iter_rules()
            if rule.endpoint.startswith("public_media.")
        ]
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0].methods - {"GET", "HEAD", "OPTIONS"}, set())

    def test_unknown_or_ineligible_public_media_returns_404(self):
        with patch("routes.public_media_routes.resolve_public_media_file", return_value=None):
            response = self.client.get("/public-media/home.hero")
        self.assertEqual(response.status_code, 404)

    def test_public_route_never_uses_an_owner_scoped_media_id(self):
        source = Path("routes/public_media_routes.py").read_text(encoding="utf-8")
        self.assertNotIn("created_by", source)
        self.assertNotIn("get_generated_media", source)
