import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import services.generated_media_service as media_service


class MockGeneratedMediaTests(unittest.TestCase):
    def test_mock_generation_creates_a_real_labelled_artifact_before_registration(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            data = media_service.GeneratedMediaInput(
                media_type="image", scene_id="HOME_HERO", character_id="athlete",
                version="mock", ai_provider="mock", prompt="development test",
                file_path="assets/athlete/generated/development/pending.svg",
            )
            with patch.object(media_service, "PROJECT_ROOT", Path(tmp_dir)), patch.object(
                media_service, "register_generated_media",
                side_effect=lambda item: {"id": 7, "file_path": item.file_path},
            ) as register:
                result = media_service.create_mock_generated_media(data, generation_job_id="job-123")
            artifact = Path(tmp_dir) / "assets/athlete/generated/development/mock-job-123.svg"
            self.assertTrue(artifact.is_file())
            self.assertIn("Mock Provider Development Artifact", artifact.read_text(encoding="utf-8"))
            self.assertEqual(result["id"], 7)
            self.assertEqual(register.call_args.args[0].mime_type, "image/svg+xml")

