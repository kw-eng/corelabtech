import unittest
from unittest.mock import Mock, patch

import services.public_media_service as public_media_service
from services.public_media_service import resolve_public_media


class PublicMediaServiceTests(unittest.TestCase):
    def setUp(self):
        public_media_service._RESOLUTION_RETRY_AT = 0

    def test_resolves_only_the_curated_eligible_media_row(self):
        cursor = Mock()
        cursor.description = [(name,) for name in (
            "role", "alt_text_en", "alt_text_pl", "id", "media_type", "mime_type",
            "file_path", "width", "height", "poster_id", "poster_mime_type",
        )]
        cursor.fetchone.return_value = (
            "home.hero", "English description", "Polski opis", 17, "image", "image/webp",
            "assets/athlete/generated/hero.webp", 1600, 900, None, None,
        )
        connection = Mock()
        connection.cursor.return_value = cursor

        with patch("services.public_media_service.db", return_value=connection):
            media = resolve_public_media("home.hero", "pl", "image")

        self.assertEqual(media["alt_text"], "Polski opis")
        self.assertNotIn("file_path", media)
        self.assertNotIn("created_by", media)
        self.assertNotIn("id", media)
        query = cursor.execute.call_args.args[0]
        self.assertIn("media.status IN ('approved', 'published')", query)
        self.assertIn("media.is_final = TRUE", query)
        self.assertIn("media.media_type IN ('image', 'video')", query)
        cursor.close.assert_called_once()
        connection.close.assert_called_once()

    def test_fails_closed_when_the_mapping_is_unavailable(self):
        with patch("services.public_media_service.db", side_effect=RuntimeError("database unavailable")):
            self.assertIsNone(resolve_public_media("home.hero", "en"))

    def test_rejects_unsupported_public_media_type_without_querying_database(self):
        with patch("services.public_media_service.db") as database:
            self.assertIsNone(resolve_public_media("home.hero", "en", "audio"))
        database.assert_not_called()

    def test_rejects_invalid_role_without_querying_database(self):
        with patch("services.public_media_service.db") as database:
            self.assertIsNone(resolve_public_media("../../home.hero", "en"))
        database.assert_not_called()

    def test_rejects_mime_type_that_does_not_match_the_public_media_type(self):
        cursor = Mock()
        cursor.description = [(name,) for name in (
            "role", "alt_text_en", "alt_text_pl", "id", "media_type", "mime_type",
            "file_path", "width", "height", "poster_id", "poster_mime_type",
        )]
        cursor.fetchone.return_value = (
            "home.hero", "English description", "Polski opis", 17, "image", "text/html",
            "assets/athlete/generated/hero.html", 1600, 900, None, None,
        )
        connection = Mock()
        connection.cursor.return_value = cursor
        with patch("services.public_media_service.db", return_value=connection):
            self.assertIsNone(resolve_public_media("home.hero", "en"))

    def test_approved_eligible_video_resolves_without_exposing_private_fields(self):
        cursor = Mock()
        cursor.description = [(name,) for name in (
            "role", "alt_text_en", "alt_text_pl", "id", "media_type", "mime_type",
            "file_path", "width", "height", "poster_id", "poster_mime_type",
        )]
        cursor.fetchone.return_value = (
            "technology.pipeline", "English video", "Polski film", 21, "video", "video/mp4",
            "assets/athlete/generated/video.mp4", 1920, 1080, 7, "text/html",
        )
        connection = Mock()
        connection.cursor.return_value = cursor
        with patch("services.public_media_service.db", return_value=connection):
            media = resolve_public_media("technology.pipeline", "en", "video")

        self.assertEqual(media["media_type"], "video")
        self.assertEqual(media["alt_text"], "English video")
        self.assertFalse(media["poster_available"])
        self.assertNotIn("file_path", media)

    def test_query_refuses_rejected_draft_and_non_final_media(self):
        cursor = Mock()
        cursor.description = [("role",)]
        cursor.fetchone.return_value = None
        connection = Mock()
        connection.cursor.return_value = cursor
        with patch("services.public_media_service.db", return_value=connection):
            self.assertIsNone(resolve_public_media("home.hero", "en"))

        query = cursor.execute.call_args.args[0]
        self.assertIn("media.status IN ('approved', 'published')", query)
        self.assertIn("media.is_final = TRUE", query)

    def test_locale_specific_alt_text_selects_english_for_non_polish_locale(self):
        cursor = Mock()
        cursor.description = [(name,) for name in (
            "role", "alt_text_en", "alt_text_pl", "id", "media_type", "mime_type",
            "file_path", "width", "height", "poster_id", "poster_mime_type",
        )]
        cursor.fetchone.return_value = (
            "home.hero", "English description", "Polski opis", 17, "image", "image/webp",
            "assets/athlete/generated/hero.webp", 1600, 900, None, None,
        )
        connection = Mock()
        connection.cursor.return_value = cursor
        with patch("services.public_media_service.db", return_value=connection):
            self.assertEqual(resolve_public_media("home.hero", "en")["alt_text"], "English description")
