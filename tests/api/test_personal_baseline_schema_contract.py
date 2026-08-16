from pathlib import Path
import unittest


class PersonalBaselineSchemaContractTests(unittest.TestCase):
    def test_migration_is_additive_and_versioned(self):
        source = Path("migrations/031_create_personal_baselines.py").read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS personal_baselines", source)
        self.assertIn("baseline_policy_version", source)
        self.assertIn("lineage_json", source)
        self.assertNotIn("DROP TABLE", source)

    def test_runner_includes_migration(self):
        source = Path("run_database_setup.py").read_text(encoding="utf-8")
        self.assertIn('"031_create_personal_baselines.py"', source)


if __name__ == "__main__":
    unittest.main()
