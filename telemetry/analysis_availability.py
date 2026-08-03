"""Determine available analyses from detected telemetry capabilities.

Availability is based on actual signals and data quality, not device brands.
"""

from __future__ import annotations

from typing import Any, Mapping


MINIMUM_USABLE_QUALITY_SCORE = 40
MINIMUM_RELIABLE_QUALITY_SCORE = 70
MINIMUM_RR_SAMPLES_FOR_HRV = 10


def determine_analysis_availability(
    capability_report: Mapping[str, Any],
) -> dict[str, Any]:
    """Determine which CoreLabTech analyses can be performed.

    Args:
        capability_report:
            Report returned by scan_telemetry_capabilities().

    Returns:
        JSON-serializable analysis availability report.
    """

    signals = dict(
        capability_report.get("signals") or {}
    )
    quality = dict(
        capability_report.get("quality") or {}
    )
    sample_counts = dict(
        capability_report.get("sample_counts") or {}
    )

    quality_score = _safe_float(
        quality.get("score")
    ) or 0.0

    has_timestamp = bool(signals.get("timestamp"))
    has_heart_rate = bool(signals.get("heart_rate"))
    has_pulse = bool(signals.get("pulse"))
    has_rr = bool(signals.get("rr_intervals"))
    has_reported_hrv = bool(
        signals.get("reported_hrv")
    )
    has_spo2 = bool(signals.get("spo2"))
    has_pressure = bool(signals.get("pressure"))
    has_session_markers = bool(
        signals.get("session_markers")
    )

    rr_sample_count = _safe_int(
        sample_counts.get("rr_intervals")
    )

    data_is_usable = (
        quality_score >= MINIMUM_USABLE_QUALITY_SCORE
    )
    data_is_reliable = (
        quality_score >= MINIMUM_RELIABLE_QUALITY_SCORE
    )

    hrv_available = (
        has_reported_hrv
        or (
            has_rr
            and rr_sample_count >= MINIMUM_RR_SAMPLES_FOR_HRV
        )
    )

    time_merge_available = (
        has_timestamp and data_is_usable
    )

    heart_rate_analysis = (
        has_heart_rate and data_is_usable
    )

    pulse_analysis = (
        has_pulse and data_is_usable
    )

    oxygen_analysis = (
        has_spo2 and data_is_usable
    )

    hrv_analysis = (
        hrv_available and data_is_usable
    )

    recovery_analysis = (
        data_is_usable
        and (
            heart_rate_analysis
            or hrv_analysis
            or pulse_analysis
        )
    )

    session_context_analysis = (
        has_pressure or has_session_markers
    )

    ai_summary = (
        data_is_usable
        and (
            heart_rate_analysis
            or oxygen_analysis
            or hrv_analysis
        )
    )

    full_session_analysis = all([
        has_timestamp,
        heart_rate_analysis,
        hrv_analysis,
        oxygen_analysis,
    ])

    hbot_response_score = (
        ai_summary
        and has_timestamp
        and (
            session_context_analysis
            or oxygen_analysis
            or hrv_analysis
        )
    )

    longitudinal_analysis = (
        heart_rate_analysis
        or hrv_analysis
        or oxygen_analysis
    )

    pdf_report = (
        ai_summary
        or recovery_analysis
        or session_context_analysis
    )

    confidence = _determine_confidence(
        quality_score=quality_score,
        has_timestamp=has_timestamp,
        heart_rate_analysis=heart_rate_analysis,
        hrv_analysis=hrv_analysis,
        oxygen_analysis=oxygen_analysis,
    )

    available = {
        "heart_rate_analysis": heart_rate_analysis,
        "pulse_analysis": pulse_analysis,
        "hrv_analysis": hrv_analysis,
        "oxygen_analysis": oxygen_analysis,
        "time_merge": time_merge_available,
        "recovery_analysis": recovery_analysis,
        "session_context_analysis": session_context_analysis,
        "ai_summary": ai_summary,
        "hbot_response_score": hbot_response_score,
        "longitudinal_analysis": longitudinal_analysis,
        "pdf_report": pdf_report,
        "full_session_analysis": full_session_analysis,
    }

    limitations = _build_limitations(
        signals=signals,
        available=available,
        rr_sample_count=rr_sample_count,
        quality_score=quality_score,
    )

    recommendations = _build_recommendations(
        signals=signals,
        available=available,
        quality_score=quality_score,
    )

    return {
        "schema_version": "analysis-availability-v1",
        "available": available,
        "analysis_level": _determine_analysis_level(
            available
        ),
        "confidence": confidence,
        "quality_sufficient": data_is_usable,
        "quality_reliable": data_is_reliable,
        "limitations": limitations,
        "recommendations": recommendations,
        "next_recommended_action": (
            recommendations[0]
            if recommendations
            else "Telemetry is ready for analysis."
        ),
    }


def build_telemetry_intelligence_report(
    capability_report: Mapping[str, Any],
) -> dict[str, Any]:
    """Combine detection and analysis availability into one API payload."""

    return {
        **dict(capability_report),
        "analysis": determine_analysis_availability(
            capability_report
        ),
    }


def _determine_analysis_level(
    available: Mapping[str, bool],
) -> int:
    """Return the highest available CoreLabTech analysis level.

    Level 1: basic/session information
    Level 2: heart-rate or pulse analysis
    Level 3: HRV analysis
    Level 4: oxygen analysis
    Level 5: full synchronized physiological response
    """

    if available.get("full_session_analysis"):
        return 5

    if available.get("oxygen_analysis"):
        return 4

    if available.get("hrv_analysis"):
        return 3

    if (
        available.get("heart_rate_analysis")
        or available.get("pulse_analysis")
    ):
        return 2

    return 1


def _determine_confidence(
    *,
    quality_score: float,
    has_timestamp: bool,
    heart_rate_analysis: bool,
    hrv_analysis: bool,
    oxygen_analysis: bool,
) -> str:
    signal_count = sum([
        heart_rate_analysis,
        hrv_analysis,
        oxygen_analysis,
    ])

    if (
        quality_score >= 85
        and has_timestamp
        and signal_count >= 2
    ):
        return "high"

    if (
        quality_score >= 60
        and has_timestamp
        and signal_count >= 1
    ):
        return "medium"

    return "low"


def _build_limitations(
    *,
    signals: Mapping[str, bool],
    available: Mapping[str, bool],
    rr_sample_count: int,
    quality_score: float,
) -> list[str]:
    limitations: list[str] = []

    if not signals.get("timestamp"):
        limitations.append(
            "Timestamp data is unavailable; time synchronization cannot be performed."
        )

    if not signals.get("heart_rate"):
        limitations.append(
            "Heart-rate telemetry is unavailable."
        )

    if (
        not signals.get("rr_intervals")
        and not signals.get("reported_hrv")
    ):
        limitations.append(
            "RR intervals and reported HRV are unavailable; HRV analysis is disabled."
        )

    elif (
        signals.get("rr_intervals")
        and rr_sample_count < MINIMUM_RR_SAMPLES_FOR_HRV
    ):
        limitations.append(
            "Too few valid RR intervals are available for reliable HRV calculation."
        )

    if not signals.get("spo2"):
        limitations.append(
            "SpO₂ telemetry is unavailable; oxygenation analysis is disabled."
        )

    if quality_score < MINIMUM_USABLE_QUALITY_SCORE:
        limitations.append(
            "Telemetry quality is too low for reliable physiological interpretation."
        )

    if not available.get("time_merge"):
        limitations.append(
            "The current source cannot be synchronized reliably with another timeline."
        )

    return limitations


def _build_recommendations(
    *,
    signals: Mapping[str, bool],
    available: Mapping[str, bool],
    quality_score: float,
) -> list[str]:
    recommendations: list[str] = []

    if not signals.get("timestamp"):
        recommendations.append(
            "Upload telemetry containing timestamps."
        )

    if not signals.get("heart_rate"):
        recommendations.append(
            "Upload a heart-rate telemetry file to enable cardiovascular trend analysis."
        )

    if not available.get("hrv_analysis"):
        recommendations.append(
            "Upload telemetry containing valid RR intervals or timestamped HRV measurements."
        )

    if not available.get("oxygen_analysis"):
        recommendations.append(
            "Upload timestamped SpO₂ and pulse data to enable oxygenation analysis."
        )

    if quality_score < MINIMUM_RELIABLE_QUALITY_SCORE:
        recommendations.append(
            "Review timestamp continuity and signal artifacts before interpreting trends."
        )

    if (
        available.get("hrv_analysis")
        and not available.get("oxygen_analysis")
    ):
        recommendations.append(
            "The current telemetry supports HRV analysis and can be merged with timestamped pulse-oximetry data."
        )

    if (
        available.get("oxygen_analysis")
        and not available.get("hrv_analysis")
    ):
        recommendations.append(
            "The current telemetry supports oxygen analysis and can be merged with timestamped HR/RR telemetry."
        )

    if available.get("full_session_analysis"):
        recommendations.append(
            "Full physiological session analysis is available."
        )

    return recommendations


def _safe_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None

    try:
        result = float(value)
    except (TypeError, ValueError):
        return None

    return result if result == result else None


def _safe_int(value: Any) -> int:
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return 0