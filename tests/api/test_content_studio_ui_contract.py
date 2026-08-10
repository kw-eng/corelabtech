import unittest
from pathlib import Path


class ContentStudioUiContractTests(unittest.TestCase):
    def setUp(self):
        self.generate_js = Path(
            "static/js/content_studio/generate.js"
        ).read_text(encoding="utf-8")
        self.media_js = Path(
            "static/js/content_studio.js"
        ).read_text(encoding="utf-8")
        self.media_css = Path(
            "static/css/content_studio/generated_media.css"
        ).read_text(encoding="utf-8")
        self.characters = Path(
            "templates/content_studio/characters.html"
        ).read_text(encoding="utf-8")

    def test_generate_uses_the_server_capability_contract(self):
        self.assertIn("/content-studio/api/provider-capabilities", self.generate_js)
        self.assertIn("loadProviderCapabilities", self.generate_js)
        self.assertNotIn('const providerCapabilities = {\n        mock:', self.generate_js)
        self.assertIn("Generation is disabled until they can be loaded.", self.generate_js)

    def test_generate_keeps_the_media_handoff_after_success(self):
        self.assertIn('mediaLink.href = "/content-studio/media"', self.generate_js)
        self.assertIn("data.media?.id", self.generate_js)

    def test_media_cards_do_not_expose_internal_file_paths(self):
        self.assertIn("Generation details", self.media_js)
        self.assertNotIn("Prompt and path", self.media_js)
        self.assertNotIn("${escapeHtml(item.file_path)}", self.media_js)

    def test_media_library_has_loading_empty_and_error_states(self):
        for text in (
            "Loading generated media",
            "No generated media yet",
            "Generated media could not be loaded",
            "data-retry-media",
        ):
            self.assertIn(text, self.media_js)

    def test_media_preview_dimensions_are_stable_and_responsive(self):
        self.assertIn("aspect-ratio: 16 / 10", self.media_css)
        self.assertIn("object-fit: contain", self.media_css)
        self.assertIn("@media (max-width: 700px)", self.media_css)

    def test_characters_page_does_not_offer_a_no_op_creation_action(self):
        self.assertNotIn("add-character-button", self.characters)
        self.assertIn("not selectable yet", self.characters)


if __name__ == "__main__":
    unittest.main()
