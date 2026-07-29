import unittest
import re

import app as app_module


class I18nSmokeTests(unittest.TestCase):
    def setUp(self):
        self.app = app_module.app
        self.app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=False,
            RATELIMIT_ENABLED=False,
        )
        self.client = self.app.test_client()

    def test_layout_uses_polish_locale_from_query_string(self):
        response = self.client.get("/?lang=pl")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('lang="pl"', html)
        self.assertIn("Start Wellness", html)
        self.assertIn("Informacja prywatno", html)
        self.assertIn("window.CORELABTECH_LOCALE = \"pl\"", html)

    def test_set_language_persists_locale_cookie(self):
        response = self.client.get("/set-language/pl?next=/")

        self.assertEqual(response.status_code, 302)
        cookie = response.headers.get("Set-Cookie", "")
        self.assertIn("corelabtech_locale=pl", cookie)

    def test_public_pages_render_with_polish_locale(self):
        public_paths = (
            "/?lang=pl",
            "/about?lang=pl",
            "/technology?lang=pl",
            "/contact?lang=pl",
            "/privacy?lang=pl",
            "/terms?lang=pl",
            "/wellness-start?lang=pl",
            "/publications?lang=pl",
        )

        for path in public_paths:
            with self.subTest(path=path):
                response = self.client.get(path)

                self.assertEqual(response.status_code, 200)
                html = response.get_data(as_text=True)
                rendered_html = re.sub(
                    r"<script\b[^>]*>.*?</script>",
                    "",
                    html,
                    flags=re.DOTALL | re.IGNORECASE,
                )
                self.assertIn('lang="pl"', html)
                self.assertNotIn("public.", rendered_html)
                self.assertNotIn("nav.", rendered_html)


if __name__ == "__main__":
    unittest.main()
