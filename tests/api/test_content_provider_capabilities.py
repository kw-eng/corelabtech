import unittest

from services.content_provider_capabilities import supports_output_type


class ContentProviderCapabilitiesTests(unittest.TestCase):
    def test_mock_provider_supports_images_but_not_video(self):
        self.assertTrue(supports_output_type("mock", "image"))
        self.assertFalse(supports_output_type("mock", "video"))
