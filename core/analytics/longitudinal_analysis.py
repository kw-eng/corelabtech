"""Longitudinal comparisons against a user's own baseline."""

from __future__ import annotations

from typing import Any

from core.analytics.trend_analysis import trend_direction


def percent_delta(
    current: float | None,
    baseline: float | None,
) -> float | None:
    if current is None or baseline in (None, 0):
        return None

    return round((current - baseline) / abs(baseline) * 100, 2)


def compare_to_baseline(
    *,
    current_features: dict[str, Any],
    baseline: dict[str, Any],
) -> dict[str, Any]:
    """Compare current session features with stored daily baseline values."""

    rmssd = as_float(current_features.get("rmssd"))
    avg_hr = as_float(current_features.get("avg_hr"))
    avg_spo2 = as_float(current_features.get("avg_spo2"))
    min_spo2 = as_float(current_features.get("min_spo2"))

    baseline_rmssd = as_float(
        baseline.get("rmssd_30d")
        or baseline.get("rmssd_14d")
        or baseline.get("rmssd_7d")
        or baseline.get("rmssd_avg")
    )
    baseline_hr = as_float(
        baseline.get("resting_hr_7d")
        or baseline.get("resting_hr")
    )
    baseline_spo2 = as_float(baseline.get("spo2_avg"))

    return {
        "rmssd_delta_percent": percent_delta(rmssd, baseline_rmssd),
        "hr_delta_percent": percent_delta(avg_hr, baseline_hr),
        "spo2_delta_percent": percent_delta(avg_spo2, baseline_spo2),
        "rmssd_direction": trend_direction(rmssd, baseline_rmssd),
        "hr_direction": trend_direction(avg_hr, baseline_hr),
        "spo2_direction": trend_direction(avg_spo2, baseline_spo2),
        "current_min_spo2": min_spo2,
        "baseline_rmssd": baseline_rmssd,
        "baseline_hr": baseline_hr,
        "baseline_spo2": baseline_spo2,
        "confidence": baseline_confidence(baseline),
    }


def baseline_confidence(baseline: dict[str, Any]) -> str:
    sessions_30d = int(as_float(baseline.get("sessions_count_30d")) or 0)
    quality = as_float(baseline.get("data_quality_score"))

    if sessions_30d >= 14 and (quality is None or quality >= 80):
        return "high"

    if sessions_30d >= 7 and (quality is None or quality >= 60):
        return "medium"

    if sessions_30d >= 3:
        return "low"

    return "insufficient"


def as_float(value: Any) -> float | None:
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None
