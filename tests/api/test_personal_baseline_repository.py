import unittest
from datetime import date

from repositories.personal_baseline_repository import load_baseline_observations, save_personal_baseline
from services.personal_baseline import calculate_personal_baseline


class Cursor:
    def __init__(self):
        self.executions = []

    def execute(self, query, params):
        self.executions.append((query, params))

    def fetchall(self):
        return [("s1", "u1", 1, "during", date(2026, 8, 15), 1.5, 80, {"avg_hrv": 40})]


class PersonalBaselineRepositoryTests(unittest.TestCase):
    def test_candidates_are_user_scoped_and_bounded_in_one_query(self):
        cursor = Cursor()
        observations = load_baseline_observations(cursor, user_id="u1", as_of=date(2026, 8, 15))
        query, params = cursor.executions[0]
        self.assertIn("WHERE user_id = %s", query)
        self.assertIn("INTERVAL '29 days'", query)
        self.assertEqual(params, ("u1", date(2026, 8, 15), date(2026, 8, 15)))
        self.assertEqual(observations[0]["user_id"], "u1")

    def test_persistence_uses_versioned_unique_contract_and_json_lineage(self):
        cursor = Cursor()
        baseline = calculate_personal_baseline(
            user_id="u1", metric="hrv_rmssd", protocol_id=1, target_ata=1.5,
            as_of=date(2026, 8, 15), observations=[],
        )
        save_personal_baseline(cursor, baseline=baseline, baseline_date=date(2026, 8, 15))
        query, params = cursor.executions[0]
        self.assertIn("personal_baselines", query)
        self.assertIn("baseline_policy_version", query)
        self.assertIn("lineage_json", query)
        self.assertEqual(query.count("%s"), len(params))


if __name__ == "__main__":
    unittest.main()
