"""Session response and recovery classification."""

from __future__ import annotations

from typing import Any


def calculate_phase_response(
    *,
    pre: dict[str, Any],
    during: dict[str, Any],
    post: dict[str, Any],
) -> dict[str, Any]:
    """Calculate PRE/DURING/POST deltas used by reports and mobile status."""

    pre_hr = as_float(pre.get("avg_hr") or pre.get("pulse"))
    during_hr = as_float(during.get("avg_hr") or during.get("pulse"))
    post_hr = as_float(post.get("avg_hr") or post.get("pulse"))

    pre_spo2 = as_float(pre.get("avg_spo2") or pre.get("spo2"))
    during_spo2 = as_float(during.get("avg_spo2") or during.get("spo2"))
    post_spo2 = as_float(post.get("avg_spo2") or post.get("spo2"))

    pre_rmssd = as_float(pre.get("rmssd") or pre.get("hrv"))
    during_rmssd = as_float(during.get("rmssd") or during.get("hrv"))
    post_rmssd = as_float(post.get("rmssd") or post.get("hrv"))

    return {
        "hr_response": delta(during_hr, pre_hr),
        "hr_recovery_delta": delta(post_hr, during_hr),
        "spo2_drop": delta(during_spo2, pre_spo2),
        "spo2_recovery_delta": delta(post_spo2, during_spo2),
        "rmssd_response": delta(during_rmssd, pre_rmssd),
        "rmssd_recovery_delta": delta(post_rmssd, during_rmssd),
    }


def classify_recovery_status(
    *,
    features: dict[str, Any],
    baseline_comparison: dict[str, Any] | None = None,
) -> str:
    """Return a mobile-friendly status for a session."""

    quality = as_float(features.get("data_quality_score"))

    if quality is not None and quality < 60:
        return "data_quality_warning"

    min_spo2 = as_float(features.get("min_spo2"))

    if min_spo2 is not None and min_spo2 < 90:
        return "elevated_load"

    comparison = baseline_comparison or {}
    rmssd_delta = as_float(comparison.get("rmssd_delta_percent"))
    hr_delta = as_float(comparison.get("hr_delta_percent"))

    if (
        rmssd_delta is not None
        and rmssd_delta <= -15
    ) or (
        hr_delta is not None
        and hr_delta >= 10
    ):
        return "elevated_load"

    recovery_delta = as_float(features.get("recovery_delta"))

    if recovery_delta is not None and recovery_delta >= 0:
        return "recovery_trend"

    return "baseline"


def delta(
    current: float | None,
    reference: float | None,
) -> float | None:
    if current is None or reference is None:
        return None

    return round(current - reference, 2)


def as_float(value: Any) -> float | None:
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None
