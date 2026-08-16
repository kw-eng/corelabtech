from __future__ import annotations

from datetime import date, datetime, timezone
import unittest

from services.personal_baseline import (
    PERSONAL_BASELINE_MIN_OBSERVATIONS,
    PERSONAL_BASELINE_POLICY_VERSION,
    calculate_personal_baseline,
)


AS_OF = date(2026, 8, 15)
CALCULATED_AT = datetime(2026, 8, 15, 12, tzinfo=timezone.utc)


def eligible_observation(
    *,
    session_id: str,
    value: float = 40.0,
    metric: str = "hrv_rmssd",
    observed_at: str = "2026-08-15",
    user_id: str = "client-a",
    protocol_id: int = 7,
    target_ata: float = 1.5,
    quality: float = 85.0,
    phase: str = "during",
) -> dict:
    features = {
        "avg_hrv": 40.0,
        "sdnn": 35.0,
        "avg_reference_heart_rate": 62.0,
        "avg_spo2": 97.0,
        "rr_source_policy": "chest_hrm_ecg_only-v1",
        "hrv_confidence": "high",
        "rr_count": 80,
        "hr_source_type": "chest_hrm",
        "hr_measurement_method": "ecg",
        "pulse_source_type": "finger_oximeter",
        "synchronized_coverage_percent": 95.0,
        "synchronized_temporal_coverage_percent": 95.0,
        "time_alignment_quality": "high",
    }
    features[{"hrv_rmssd": "avg_hrv", "hrv_sdnn": "sdnn", "reference_heart_rate": "avg_reference_heart_rate", "spo2_during_session": "avg_spo2"}[metric]] = value
    return {
        "session_id": session_id, "user_id": user_id, "protocol_id": protocol_id,
        "target_ata": target_ata, "observed_at": observed_at, "phase": phase,
        "data_quality_score": quality, "features": features,
    }


def baseline(metric: str = "hrv_rmssd", observations: list[dict] | None = None, **scope) -> dict:
    return calculate_personal_baseline(
        user_id=scope.get("user_id", "client-a"), metric=metric,
        observations=observations or [], protocol_id=scope.get("protocol_id", 7),
        target_ata=scope.get("target_ata", 1.5), as_of=AS_OF,
        calculated_at=CALCULATED_AT,
    )


class PersonalBaselineTests(unittest.TestCase):
    def test_requires_explicit_minimum_observation_threshold(self):
        for count in range(PERSONAL_BASELINE_MIN_OBSERVATIONS):
            result = baseline(observations=[eligible_observation(session_id=str(index)) for index in range(count)])
            self.assertEqual(result["status"], "insufficient_evidence")
            self.assertIsNone(result["baseline_value"])
        result = baseline(observations=[eligible_observation(session_id=str(index), value=40 + index) for index in range(PERSONAL_BASELINE_MIN_OBSERVATIONS)])
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["baseline_value"], 41.0)

    def test_policy_version_window_and_recalculation_are_deterministic(self):
        observations = [eligible_observation(session_id=str(index), value=40 + index) for index in range(3)]
        first = baseline(observations=observations)
        second = baseline(observations=observations)
        self.assertEqual(first, second)
        self.assertEqual(first["baseline_policy_version"], PERSONAL_BASELINE_POLICY_VERSION)
        self.assertEqual(first["window_days"], 30)
        self.assertEqual(first["window_start"], "2026-07-17")

    def test_enforces_quality_protocol_window_and_missing_or_invalid_values(self):
        candidates = [
            eligible_observation(session_id="quality", quality=69),
            eligible_observation(session_id="protocol", protocol_id=8),
            eligible_observation(session_id="ata", target_ata=1.6),
            eligible_observation(session_id="old", observed_at="2026-07-16"),
            eligible_observation(session_id="missing"),
            eligible_observation(session_id="invalid", value=600),
        ]
        candidates[4]["features"]["avg_hrv"] = None
        result = baseline(observations=candidates)
        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertEqual(result["candidate_observation_count"], 5)
        self.assertEqual(result["rejection_summary"], {
            "incompatible_protocol": 2, "insufficient_quality": 1,
            "invalid_value": 1, "missing_metric": 1,
        })

    def test_enforces_hrv_rr_provenance_and_snapshot_exclusion(self):
        invalid_source = eligible_observation(session_id="source")
        invalid_source["features"]["rr_source_policy"] = "unknown"
        low_rr = eligible_observation(session_id="rr")
        low_rr["features"]["rr_count"] = 3
        snapshot = eligible_observation(session_id="snapshot", phase="check_in")
        result = baseline(observations=[invalid_source, low_rr, snapshot])
        self.assertEqual(result["rejection_summary"], {
            "insufficient_coverage": 1, "snapshot_excluded": 1,
            "unsupported_provenance": 1,
        })

    def test_pulse_cannot_substitute_for_reference_hr(self):
        observations = [eligible_observation(session_id=str(index), metric="reference_heart_rate", value=60 + index) for index in range(3)]
        for item in observations:
            item["features"]["hr_source_type"] = "unknown"
            item["features"]["avg_reference_heart_rate"] = None
            item["features"]["avg_pulse"] = 60
        result = baseline(metric="reference_heart_rate", observations=observations)
        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertEqual(result["rejection_summary"], {"missing_metric": 3})

    def test_spo2_requires_distinct_synchronized_oximeter_semantics(self):
        observations = [eligible_observation(session_id=str(index), metric="spo2_during_session", value=97) for index in range(3)]
        observations[0]["features"]["pulse_source_type"] = "unknown"
        observations[1]["features"]["synchronized_coverage_percent"] = 50
        observations[2]["phase"] = "recovery"
        result = baseline(metric="spo2_during_session", observations=observations)
        self.assertEqual(result["rejection_summary"], {
            "insufficient_coverage": 1, "snapshot_excluded": 1,
            "unsupported_provenance": 1,
        })

    def test_outlier_rejection_requires_sufficient_cohort_and_keeps_lineage(self):
        observations = [eligible_observation(session_id=str(index), value=40 + index) for index in range(5)]
        observations.append(eligible_observation(session_id="outlier", value=200))
        result = baseline(observations=observations)
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["rejection_summary"], {"outlier_excluded": 1})
        self.assertIn({"session_id": "outlier", "reason": "outlier_excluded"}, result["rejections"])
        self.assertNotIn("outlier", [entry["session_id"] for entry in result["eligible_session_refs"]])

    def test_ineligible_and_other_user_data_cannot_change_a_baseline(self):
        eligible = [eligible_observation(session_id=str(index), value=40 + index) for index in range(3)]
        initial = baseline(observations=eligible)
        ineligible = eligible_observation(session_id="ineligible", value=300, quality=20)
        other_user = eligible_observation(session_id="other", value=300, user_id="client-b")
        updated = baseline(observations=eligible + [ineligible, other_user])
        self.assertEqual(initial["baseline_value"], updated["baseline_value"])
        self.assertEqual(initial["eligible_observation_count"], updated["eligible_observation_count"])


if __name__ == "__main__":
    unittest.main()
