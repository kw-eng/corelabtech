import unittest
from pathlib import Path


class PublicMediaSchemaContractTests(unittest.TestCase):
    def test_role_is_the_single_active_mapping_key(self):
        source = Path("migrations/029_create_public_media_assets.py").read_text(encoding="utf-8")
        self.assertIn("role VARCHAR(128) PRIMARY KEY", source)

    def test_forward_hardening_declares_restrictive_foreign_keys_and_timestamp_trigger(self):
        source = Path("migrations/030_harden_public_media_assets.py").read_text(encoding="utf-8")
        self.assertEqual(source.count("ON DELETE RESTRICT"), 2)
        self.assertIn("touch_public_media_assets_updated_at", source)
        self.assertIn("BEFORE UPDATE ON public_media_assets", source)

    def test_migration_runner_contains_the_forward_only_hardening_step(self):
        source = Path("run_database_setup.py").read_text(encoding="utf-8")
        self.assertIn('"030_harden_public_media_assets.py"', source)
