import unittest

from services.series_service import compare_session_windows, series_evidence_level


def analyses(count):
    return [
        {
            "overall_score": 80 + index,
            "data_quality_score": 70 + index,
            "avg_reference_heart_rate": 60 + index,
            "avg_hrv": 30 + index,
            "avg_spo2": 96 + index / 10,
        }
        for index in range(count)
    ]


class SeriesReportWindowTests(unittest.TestCase):
    def test_one_session_uses_a_single_session_summary(self):
        comparison = compare_session_windows(analyses(1))
        self.assertFalse(comparison["available"])
        self.assertEqual(comparison["label"], "Single-session summary")

    def test_three_sessions_compares_first_and_latest(self):
        comparison = compare_session_windows(analyses(3))
        self.assertTrue(comparison["available"])
        self.assertEqual(comparison["window_size"], 1)
        self.assertIn("first available", comparison["label"].lower())

    def test_five_sessions_uses_available_groups(self):
        comparison = compare_session_windows(analyses(5))
        self.assertEqual(comparison["window_size"], 2)
        self.assertEqual(comparison["first_count"], 2)
        self.assertEqual(comparison["last_count"], 2)

    def test_ten_sessions_uses_first_five_and_last_five(self):
        comparison = compare_session_windows(analyses(10))
        self.assertEqual(comparison["window_size"], 5)
        self.assertEqual(comparison["label"], "First 5 vs last 5 sessions")

    def test_evidence_levels_do_not_overstate_small_series(self):
        self.assertEqual(series_evidence_level(1), "insufficient")
        self.assertEqual(series_evidence_level(3), "preliminary")
        self.assertEqual(series_evidence_level(5), "emerging")
        self.assertEqual(series_evidence_level(10), "established")
