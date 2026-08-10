"""Deterministic PRE/DURING/POST wellness-response facts.

This module deliberately does not alter ``wellness-rules-v2`` scores.  It
describes only measurements and self-reported context already captured by the
session workflow, and leaves unavailable comparisons as ``None``.
"""

from __future__ import annotations

from math import isfinite
from typing import Any


RESPONSE_MODEL_VERSION = "wellness-response-v1"


def build_session_response(
    *,
    session_context: dict[str, Any] | None,
    features: dict[str, Any] | None,
    data_quality_score: float | int | None,
    analysis_confidence: str | None,
    quality_warnings: list[str] | None,
) -> dict[str, Any]:
    """Build a factual response view without inferring treatment effects."""

    context = session_context or {}
    values = features or {}
    pre_source = context.get("pre_check_in") or {}
    post_source = context.get("post_check_out") or {}
    warnings = list(quality_warnings or [])
    normalized_data_quality_score = numeric_value(data_quality_score)

    pre = {
        "spo2": value_for(pre_source, "spo2", "avg_spo2"),
        "heart_rate_bpm": value_for(
            pre_source, "heart_rate_bpm", "heart_rate", "pulse"
        ),
        "hrv_rmssd_ms": value_for(pre_source, "hrv_rmssd", "rmssd", "hrv"),
    }
    during = {
        "avg_spo2": numeric_value(values.get("avg_spo2")),
        "min_spo2": numeric_value(values.get("min_spo2")),
        "avg_heart_rate_bpm": value_for(
            values, "avg_reference_heart_rate", "avg_heart_rate"
        ),
        "avg_pulse_bpm": numeric_value(values.get("avg_pulse")),
        "hrv_rmssd_ms": numeric_value(values.get("avg_hrv")),
        "duration_min": numeric_value(
            (context.get("session_timing") or {}).get("total_duration_min")
        ),
        "data_quality_score": normalized_data_quality_score,
        "synchronization_percent": numeric_value(values.get("match_rate")),
    }
    post = {
        "spo2": value_for(post_source, "spo2", "avg_spo2"),
        "heart_rate_bpm": value_for(
            post_source, "heart_rate_bpm", "heart_rate", "pulse"
        ),
        "hrv_rmssd_ms": value_for(post_source, "hrv_rmssd", "rmssd", "hrv"),
    }
    deltas = {
        "spo2_percentage_points": difference(post["spo2"], pre["spo2"]),
        "heart_rate_bpm": difference(
            post["heart_rate_bpm"], pre["heart_rate_bpm"]
        ),
        "hrv_rmssd_ms": difference(
            post["hrv_rmssd_ms"], pre["hrv_rmssd_ms"]
        ),
    }
    delta_availability = {
        key: value is not None
        for key, value in deltas.items()
    }

    return {
        "version": RESPONSE_MODEL_VERSION,
        "pre": pre,
        "during": during,
        "post": post,
        "deltas": deltas,
        "availability": {
            "deltas": delta_availability,
            "available_delta_count": sum(delta_availability.values()),
            "possible_delta_count": len(deltas),
        },
        "subjective_context": {
            "pre": select_subjective(
                pre_source,
                "sleep_hours", "sleep_quality", "stress_level",
                "training_load_24h", "fatigue_level", "session_goal",
            ),
            "post": select_subjective(
                post_source,
                "energy_level", "relaxation_level", "fatigue_level", "discomfort",
            ),
        },
        "confidence": response_confidence(
            data_quality_score=normalized_data_quality_score,
            analysis_confidence=analysis_confidence,
            warnings=warnings,
            available_delta_count=sum(delta_availability.values()),
        ),
        "data_quality": {
            "score": normalized_data_quality_score,
            "analysis_confidence": analysis_confidence,
            "warnings": warnings,
        },
        "limitations": response_limitations(
            pre=pre,
            post=post,
            warnings=warnings,
        ),
    }


def value_for(source: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = numeric_value(source.get(key))
        if value not in (None, ""):
            return value
    return None


def numeric_value(value: Any) -> float | int | None:
    """Normalize objective measurements without coercing invalid data to zero."""

    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not isfinite(numeric):
        return None
    return int(numeric) if numeric.is_integer() else numeric


def difference(post: Any, pre: Any) -> float | int | None:
    """Return post minus pre only when both captured values are numeric."""

    try:
        result = float(post) - float(pre)
    except (TypeError, ValueError):
        return None
    return int(result) if result.is_integer() else round(result, 2)


def select_subjective(source: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {
        key: source[key]
        for key in keys
        if source.get(key) not in (None, "")
    }


def response_confidence(
    *,
    data_quality_score: float | int | None,
    analysis_confidence: str | None,
    warnings: list[str],
    available_delta_count: int,
) -> str:
    """Use existing quality evidence; never elevate absent PRE/POST data."""

    if available_delta_count == 0:
        return "insufficient"
    if data_quality_score is None or data_quality_score < 60:
        return "limited"
    if "sensor_mismatch" in warnings or "sensor_alignment_warning" in warnings:
        return "limited"
    if analysis_confidence in {"low", "unavailable"}:
        return "limited"
    if (
        available_delta_count >= 2
        and data_quality_score >= 80
        and analysis_confidence == "high"
    ):
        return "high"
    return "medium"


def response_limitations(
    *,
    pre: dict[str, Any],
    post: dict[str, Any],
    warnings: list[str],
) -> list[str]:
    limitations = list(warnings)
    if not any(value is not None for value in pre.values()):
        limitations.append("pre_measurements_unavailable")
    if not any(value is not None for value in post.values()):
        limitations.append("post_measurements_unavailable")
    return limitations
