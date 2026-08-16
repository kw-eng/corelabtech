from datetime import date
from unittest import TestCase
from unittest.mock import patch

from services.analysis_service import refresh_personal_baselines_safely


class CapturingCursor:
    def __init__(self):
        self.statements = []

    def execute(self, statement):
        self.statements.append(statement)


class PersonalBaselineIntegrationTests(TestCase):
    def test_baseline_refresh_failure_rolls_back_only_its_savepoint(self):
        cursor = CapturingCursor()
        with patch(
            "services.analysis_service.refresh_personal_baselines",
            side_effect=RuntimeError("storage unavailable"),
        ):
            refresh_personal_baselines_safely(
                cursor,
                user_id="isolated-client",
                protocol_id=2,
                target_ata=1.5,
                baseline_date=date(2026, 8, 16),
            )

        self.assertEqual(
            cursor.statements,
            [
                "SAVEPOINT personal_baseline_refresh",
                "ROLLBACK TO SAVEPOINT personal_baseline_refresh",
            ],
        )

    def test_successful_baseline_refresh_releases_its_savepoint(self):
        cursor = CapturingCursor()
        with patch("services.analysis_service.refresh_personal_baselines"):
            refresh_personal_baselines_safely(
                cursor,
                user_id="isolated-client",
                protocol_id=2,
                target_ata=1.5,
                baseline_date=date(2026, 8, 16),
            )

        self.assertEqual(
            cursor.statements,
            [
                "SAVEPOINT personal_baseline_refresh",
                "RELEASE SAVEPOINT personal_baseline_refresh",
            ],
        )
