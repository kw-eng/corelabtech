"""Evidence-governed personal physiological baseline calculations.

This module deliberately does not consume wellness scores, contextual
snapshots, population ranges, or recovery/progress classifications.  It
calculates a user's own reference only from comparable, eligible session
observations and returns enough lineage for an operator-side audit trail.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
from statistics import median
from typing import Any


PERSONAL_BASELINE_POLICY_VERSION = "personal-baseline-v1"
PERSONAL_BASELINE_WINDOW_DAYS = 30
PERSONAL_BASELINE_MIN_OBSERVATIONS = 3
PERSONAL_BASELINE_QUALITY_MINIMUM = 70.0
PERSONAL_BASELINE_OUTLIER_MIN_OBSERVATIONS = 5
PERSONAL_BASELINE_OUTLIER_MAD_Z_LIMIT = 3.5
APPROVED_RR_SOURCE_POLICY = "chest_hrm_ecg_only-v1"
APPROVED_HRV_CONFIDENCE = {"medium", "high"}
APPROVED_SPO2_SOURCES = {"finger_oximeter", "pulse_oximeter"}

METRIC_DEFINITIONS = {
    "hrv_rmssd": {"unit": "ms"},
    "hrv_sdnn": {"unit": "ms"},
    "reference_heart_rate": {"unit": "bpm"},
    "spo2_during_session": {"unit": "%"},
}


def calculate_personal_baseline(
    *,
    user_id: str,
    metric: str,
    observations: list[dict[str, Any]],
    protocol_id: int | None,
    target_ata: float | None,
    as_of: date,
    calculated_at: datetime | None = None,
) -> dict[str, Any]:
    """Return a deterministic, audit-ready baseline result.

    ``observations`` is intentionally a normalized repository boundary.  The
    calculation is independently testable and never reaches into raw storage.
    The selected protocol is an exact scope; target ATA is compared only when
    both observations provide it, using a small measurement tolerance.
    """

    if metric not in METRIC_DEFINITIONS:
        raise ValueError(f"Unsupported personal baseline metric: {metric}")

    calculated_at = calculated_at or datetime.now(timezone.utc)
    window_start = as_of.fromordinal(
        as_of.toordinal() - (PERSONAL_BASELINE_WINDOW_DAYS - 1)
    )
    considered: list[dict[str, Any]] = []
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []

    for observation in observations:
        if observation.get("user_id") != user_id:
            # Repository queries are already user-scoped.  Retaining this
            # guard prevents accidental cross-user use by future callers.
            continue
        observed_on = observation_date(observation)
        if observed_on is None or not window_start <= observed_on <= as_of:
            continue
        considered.append(observation)
        reason = eligibility_reason(
            metric=metric,
            observation=observation,
            protocol_id=protocol_id,
            target_ata=target_ata,
        )
        if reason:
            rejected.append(rejection_ref(observation, reason))
            continue
        accepted.append(observation)

    accepted, outlier_rejections = exclude_metric_outliers(
        metric=metric,
        observations=accepted,
    )
    rejected.extend(outlier_rejections)
    values = [metric_value(metric, observation) for observation in accepted]
    values = [value for value in values if value is not None]
    status = (
        "available"
        if len(values) >= PERSONAL_BASELINE_MIN_OBSERVATIONS
        else "insufficient_evidence"
    )
    rejection_summary = dict(sorted(Counter(item["reason"] for item in rejected).items()))
    baseline_value = round(float(median(values)), 2) if status == "available" else None

    return {
        "user_id": user_id,
        "metric": metric,
        "metric_unit": METRIC_DEFINITIONS[metric]["unit"],
        "status": status,
        "baseline_value": baseline_value,
        "baseline_center": baseline_value,
        "baseline_lower_bound": round(min(values), 2) if status == "available" else None,
        "baseline_upper_bound": round(max(values), 2) if status == "available" else None,
        "eligible_observation_count": len(values),
        "candidate_observation_count": len(considered),
        "rejected_observation_count": len(rejected),
        "window_days": PERSONAL_BASELINE_WINDOW_DAYS,
        "window_start": window_start.isoformat(),
        "valid_from": window_start.isoformat(),
        "protocol_scope": {
            "protocol_id": protocol_id,
            "target_ata": target_ata,
            "phase": "during",
        },
        "provenance_scope": provenance_scope(metric),
        "quality_policy": {
            "minimum_data_quality_score": PERSONAL_BASELINE_QUALITY_MINIMUM,
        },
        "outlier_policy": {
            "method": "mad_modified_z_score",
            "minimum_observations": PERSONAL_BASELINE_OUTLIER_MIN_OBSERVATIONS,
            "z_score_limit": PERSONAL_BASELINE_OUTLIER_MAD_Z_LIMIT,
            "borderline_policy": "retain_at_or_below_limit",
        },
        "baseline_policy_version": PERSONAL_BASELINE_POLICY_VERSION,
        "calculated_at": calculated_at.isoformat(),
        "eligible_session_refs": [safe_session_ref(item) for item in accepted],
        "rejections": rejected,
        "rejection_summary": rejection_summary,
        "evidence": {
            "minimum_observations": PERSONAL_BASELINE_MIN_OBSERVATIONS,
            "sufficient": status == "available",
        },
    }


def eligibility_reason(*, metric: str, observation: dict[str, Any], protocol_id: int | None, target_ata: float | None) -> str | None:
    """Return the first stable reason an observation cannot enter a metric."""

    if observation.get("phase") != "during":
        return "snapshot_excluded"
    if observation.get("protocol_id") != protocol_id or not ata_compatible(
        observation.get("target_ata"), target_ata
    ):
        return "incompatible_protocol"
    if numeric(observation.get("data_quality_score")) is None or numeric(observation.get("data_quality_score")) < PERSONAL_BASELINE_QUALITY_MINIMUM:
        return "insufficient_quality"
    features = observation.get("features") or {}
    value = metric_value(metric, observation)
    if value is None:
        return "missing_metric"
    if not valid_metric_value(metric, value):
        return "invalid_value"
    if metric.startswith("hrv_"):
        if features.get("rr_source_policy") != APPROVED_RR_SOURCE_POLICY:
            return "unsupported_provenance"
        if features.get("hrv_confidence") not in APPROVED_HRV_CONFIDENCE or int(features.get("rr_count") or 0) < 20:
            return "insufficient_coverage"
    elif metric == "reference_heart_rate":
        if not (
            features.get("hr_source_type") == "chest_hrm"
            and features.get("hr_measurement_method") == "ecg"
        ):
            return "unsupported_provenance"
    elif metric == "spo2_during_session":
        if features.get("pulse_source_type") not in APPROVED_SPO2_SOURCES:
            return "unsupported_provenance"
        if (
            numeric(features.get("synchronized_coverage_percent")) is None
            or numeric(features.get("synchronized_coverage_percent")) < 80
            or numeric(features.get("synchronized_temporal_coverage_percent")) is None
            or numeric(features.get("synchronized_temporal_coverage_percent")) < 80
            or features.get("time_alignment_quality") not in {"high", "medium"}
        ):
            return "insufficient_coverage"
    return None


def metric_value(metric: str, observation: dict[str, Any]) -> float | None:
    features = observation.get("features") or {}
    keys = {
        "hrv_rmssd": "avg_hrv",
        "hrv_sdnn": "sdnn",
        "reference_heart_rate": "avg_reference_heart_rate",
        "spo2_during_session": "avg_spo2",
    }
    return numeric(features.get(keys[metric]))


def valid_metric_value(metric: str, value: float) -> bool:
    ranges = {
        "hrv_rmssd": (0.0, 500.0),
        "hrv_sdnn": (0.0, 500.0),
        "reference_heart_rate": (20.0, 240.0),
        "spo2_during_session": (50.0, 100.0),
    }
    lower, upper = ranges[metric]
    return lower <= value <= upper


def exclude_metric_outliers(*, metric: str, observations: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Exclude only unambiguous MAD outliers in a sufficiently large cohort."""

    if len(observations) < PERSONAL_BASELINE_OUTLIER_MIN_OBSERVATIONS:
        return observations, []
    values = [metric_value(metric, item) for item in observations]
    center = median(values)
    mad = median(abs(value - center) for value in values)
    if mad == 0:
        return observations, []
    retained, rejected = [], []
    for item, value in zip(observations, values):
        modified_z_score = 0.6745 * (value - center) / mad
        if abs(modified_z_score) > PERSONAL_BASELINE_OUTLIER_MAD_Z_LIMIT:
            rejected.append(rejection_ref(item, "outlier_excluded"))
        else:
            retained.append(item)
    return retained, rejected


def observation_date(observation: dict[str, Any]) -> date | None:
    value = observation.get("observed_at")
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        return None


def ata_compatible(candidate: Any, expected: float | None) -> bool:
    candidate_value = numeric(candidate)
    expected_value = numeric(expected)
    if candidate_value is None or expected_value is None:
        return candidate_value is expected_value
    return abs(candidate_value - expected_value) <= 0.05


def numeric(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def safe_session_ref(observation: dict[str, Any]) -> dict[str, str | None]:
    return {"session_id": str(observation.get("session_id") or ""), "observed_at": str(observation.get("observed_at") or "")}


def rejection_ref(observation: dict[str, Any], reason: str) -> dict[str, str]:
    return {"session_id": str(observation.get("session_id") or ""), "reason": reason}


def provenance_scope(metric: str) -> dict[str, str]:
    if metric.startswith("hrv_"):
        return {"rr_source_policy": APPROVED_RR_SOURCE_POLICY}
    if metric == "reference_heart_rate":
        return {"hr_source_type": "chest_hrm", "hr_measurement_method": "ecg"}
    return {"spo2_source": "approved_synchronized_pulse_oximeter"}
