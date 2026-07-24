"""Rule-based wellness analysis for merged session telemetry.

The service reads synchronized FIT/CSV measurements, computes quality and
session physiology signals, and persists an AI-style result for dashboards/reports.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date
from statistics import mean
from typing import Any

from database_postgres import db
from core.analytics.adaptation_analysis import classify_recovery_status

from repositories.analysis_repository import (
    complete_ai_result,
    create_ai_result,
)

from repositories.merge_repository import (
    get_latest_completed_merge_job,
    load_merged_measurements,
)
from repositories.wellness_repository import (
    refresh_daily_baseline,
    upsert_session_features,
)


MODEL_NAME = "CoreLabTech Wellness Session Analysis"
MODEL_VERSION = "wellness-rules-v1"
WELLNESS_DISCLAIMER = (
    "Wellness and educational insight only. "
    "Not intended to diagnose, treat, cure, or prevent disease."
)


class AnalysisError(Exception):
    """Base class for controlled analysis errors."""

    pass


class AnalysisInputMissingError(AnalysisError):
    """Raised when a session does not yet have usable merged telemetry."""

    pass


@dataclass(frozen=True)
class AnalysisResult:
    """API-friendly wrapper around one saved AI result."""

    ai_result_id: int
    merge_id: int
    session_id: str
    result: dict[str, Any]

    def to_dict(self) -> dict:
        return {
            "ai_result_id": self.ai_result_id,
            "merge_id": self.merge_id,
            "session_id": self.session_id,
            **self.result,
        }


def run_session_analysis(
    *,
    session_id: str,
    user_id: str | None = None,
) -> AnalysisResult:
    """Run analysis for the latest completed merge job of a session."""

    connection = db()
    cursor = connection.cursor()

    try:
        merge_job = get_latest_completed_merge_job(
            cursor,
            session_id=session_id,
        )

        if not merge_job:
            raise AnalysisInputMissingError(
                "No completed merge job found"
            )

        measurements = load_merged_measurements(
            cursor,
            merge_id=merge_job["merge_id"],
        )

        usable = [
            row
            for row in measurements
            if row.get("synchronized") is True
        ]

        if not usable:
            raise AnalysisInputMissingError(
                "Merged timeline contains no synchronized records"
            )

        final_user_id = (
            user_id
            or merge_job.get("user_id")
            or session_id
        )

        session_context = load_session_context(
            cursor,
            session_id=session_id,
        )

        result = analyze_measurements(
            measurements=measurements,
            usable=usable,
            session_context=session_context,
        )

        ai_result_id = create_ai_result(
            cursor,
            merge_id=merge_job["merge_id"],
            session_id=session_id,
            user_id=final_user_id,
            model_name=MODEL_NAME,
            model_version=MODEL_VERSION,
        )

        complete_ai_result(
            cursor,
            ai_result_id=ai_result_id,
            result=result,
        )

        upsert_session_features(
            cursor,
            session_id=session_id,
            user_id=final_user_id,
            phase="during",
            window_start=result["features"].get("window_start"),
            window_end=result["features"].get("window_end"),
            features=result["features"],
            result=result,
        )

        refresh_daily_baseline(
            cursor,
            user_id=final_user_id,
            baseline_date=(
                result["features"].get("window_start").date()
                if result["features"].get("window_start")
                else date.today()
            ),
        )

        connection.commit()

        return AnalysisResult(
            ai_result_id=ai_result_id,
            merge_id=merge_job["merge_id"],
            session_id=session_id,
            result=result,
        )

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()


def analyze_measurements(
    *,
    measurements: list[dict[str, Any]],
    usable: list[dict[str, Any]],
    session_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Calculate scores and warnings from synchronized measurements.

    The model is intentionally deterministic and wellness-oriented: it applies
    thresholds for oxygenation trends, load indicators and sensor mismatch.
    """

    spo2_values = numeric_values(
        usable,
        "spo2",
    )

    hr_values = numeric_values(
        usable,
        "heart_rate",
    )

    pulse_values = numeric_values(
        usable,
        "pulse",
    )

    hrv_values = numeric_values(
        usable,
        "hrv",
    )

    differences = [
        abs(
            float(row["heart_rate"])
            - float(row["pulse"])
        )
        for row in usable
        if (
            row.get("heart_rate") is not None
            and row.get("pulse") is not None
        )
    ]

    min_spo2 = minimum(spo2_values)
    avg_hrv = average(hrv_values)
    max_hr = maximum(hr_values)
    max_difference = maximum(differences)
    rr_values = numeric_values(
        usable,
        "rr_interval",
    )
    window_start = first_timestamp(usable)
    window_end = last_timestamp(usable)

    hypoxia_detected = (
        min_spo2 is not None
        and min_spo2 < 90
    )

    stress_detected = (
        avg_hrv is not None
        and avg_hrv < 30
    )

    cardiovascular_warning = (
        max_hr is not None
        and max_hr > 160
    )

    sensor_mismatch = (
        max_difference is not None
        and max_difference > 20
    )

    score = 100
    reasons = []
    positive_findings = []

    if hypoxia_detected:
        score -= 40
        reasons.append(
            "SpO2 dropped below the configured low oxygenation threshold"
        )
    elif min_spo2 is not None and min_spo2 < 94:
        score -= 15
        reasons.append(
            "SpO2 was below the preferred wellness range"
        )
    else:
        positive_findings.append(
            "SpO2 remained stable and within the expected range"
        )

    if stress_detected:
        score -= 20
        reasons.append(
            "Average HRV was below the configured recovery threshold"
        )

    if cardiovascular_warning:
        score -= 15
        reasons.append(
            "Heart rate exceeded the configured high-load threshold"
        )

    if sensor_mismatch:
        score -= 10
        reasons.append(
            "Notable discrepancy between wearable heart rate "
            "and pulse oximeter pulse"
        )

    score = max(0, min(score, 100))

    match_rate = round(
        len(usable) / len(measurements) * 100,
        2,
    )

    quality_warnings = build_quality_warnings(
        samples_total=len(measurements),
        samples_synchronized=len(usable),
        match_rate=match_rate,
        has_hrv=bool(hrv_values or rr_values),
        has_spo2=bool(spo2_values),
        sensor_mismatch=sensor_mismatch,
    )

    data_quality_score = calculate_data_quality_score(
        match_rate=match_rate,
        quality_warnings=quality_warnings,
    )

    context_features = summarize_session_context(session_context or {})

    features = {
        "samples_total": len(measurements),
        "samples_synchronized": len(usable),
        "match_rate": match_rate,
        "quality_warnings": quality_warnings,
        "window_start": window_start,
        "window_end": window_end,

        "avg_spo2": average(spo2_values),
        "min_spo2": min_spo2,
        "max_spo2": maximum(spo2_values),

        "avg_heart_rate": average(hr_values),
        "min_heart_rate": minimum(hr_values),
        "max_heart_rate": max_hr,

        "avg_pulse": average(pulse_values),
        "min_pulse": minimum(pulse_values),
        "max_pulse": maximum(pulse_values),

        "avg_hrv": avg_hrv,
        "min_hrv": minimum(hrv_values),
        "max_hrv": maximum(hrv_values),
        "rr_count": len(rr_values),
        "sdnn": standard_deviation(rr_values),
        "pnn50": pnn50(rr_values),
        "artifact_ratio": artifact_ratio(rr_values),

        "avg_hr_pulse_difference": average(
            differences
        ),
        "max_hr_pulse_difference": max_difference,
        "session_context": session_context or {},
        "context_features": context_features,
    }

    anomaly_detected = bool(
        hypoxia_detected
        or stress_detected
        or cardiovascular_warning
        or sensor_mismatch
    )
    oxygenation_drop = bool(
        min_spo2 is not None
        and min_spo2 < 94
    )
    elevated_load = bool(
        stress_detected
        or cardiovascular_warning
        or oxygenation_drop
    )
    wellness_status = (
        "data_quality_warning"
        if data_quality_score < 60
        else (
        "elevated_load"
        if elevated_load
        else classify_recovery_status(
            features={
                "data_quality_score": data_quality_score,
                "min_spo2": min_spo2,
                "recovery_delta": None,
            },
        )
        )
    )

    summary = build_research_summary(
        reasons=reasons,
        positive_findings=positive_findings,
        sensor_mismatch=sensor_mismatch,
        max_difference=max_difference,
    )

    recommendations = build_recommendations(
        anomaly_detected=anomaly_detected,
        sensor_mismatch=sensor_mismatch,
        context_features=context_features,
    )

    return {
        "overall_score": score,
        "recovery_score": None,
        "stress_score": (
            100 - min(100, max(0, 30 - avg_hrv) * 3)
            if avg_hrv is not None
            else None
        ),
        "hypoxia_score": (
            min_spo2
            if min_spo2 is not None
            else None
        ),
        "cardiovascular_score": (
            max_hr
            if max_hr is not None
            else None
        ),
        "data_quality_score": data_quality_score,

        "anomaly_detected": anomaly_detected,
        "stress_detected": stress_detected,
        "hypoxia_detected": hypoxia_detected,
        "arrhythmia_detected": False,

        "product_mode": "wellness",
        "wellness_status": wellness_status,
        "session_flagged": anomaly_detected,
        "elevated_load": elevated_load,
        "oxygenation_drop": oxygenation_drop,
        "sensor_alignment_warning": sensor_mismatch,
        "wellness_flags": {
            "session_flagged": anomaly_detected,
            "elevated_load": elevated_load,
            "oxygenation_drop": oxygenation_drop,
            "sensor_alignment_warning": sensor_mismatch,
            "data_quality_warning": wellness_status == "data_quality_warning",
        },
        "quality_warnings": quality_warnings,
        "session_context": session_context or {},
        "context_features": context_features,

        "summary": (
            summary
            or "No significant deviations detected."
        ),

        "recommendations": recommendations,

        "features": features,

        "timeline": [
            serialize_timeline_row(row)
            for row in measurements
        ],

        "reasons": reasons,
        "positive_findings": positive_findings,

        "model_name": MODEL_NAME,
        "model_version": MODEL_VERSION,

        "research_only": True,
        "medical_disclaimer": WELLNESS_DISCLAIMER,
        "wellness_disclaimer": WELLNESS_DISCLAIMER,
    }


def numeric_values(
    rows: list[dict[str, Any]],
    key: str,
) -> list[float]:
    """Extract numeric values for one measurement key, skipping bad data."""

    result = []

    for row in rows:
        value = row.get(key)

        if value is None:
            continue

        try:
            result.append(float(value))
        except (TypeError, ValueError):
            continue

    return result


def first_timestamp(
    rows: list[dict[str, Any]],
) -> Any:
    timestamps = [
        row.get("timestamp")
        for row in rows
        if row.get("timestamp") is not None
    ]
    return min(timestamps) if timestamps else None


def last_timestamp(
    rows: list[dict[str, Any]],
) -> Any:
    timestamps = [
        row.get("timestamp")
        for row in rows
        if row.get("timestamp") is not None
    ]
    return max(timestamps) if timestamps else None


def standard_deviation(
    values: list[float],
) -> float | None:
    if len(values) < 2:
        return None

    avg = mean(values)
    variance = sum((value - avg) ** 2 for value in values) / (len(values) - 1)
    return round(variance ** 0.5, 2)


def pnn50(
    rr_values: list[float],
) -> float | None:
    if len(rr_values) < 2:
        return None

    differences = [
        abs(current - previous)
        for previous, current in zip(rr_values, rr_values[1:])
    ]
    if not differences:
        return None

    over_50 = sum(1 for value in differences if value > 50)
    return round(over_50 / len(differences) * 100, 2)


def artifact_ratio(
    rr_values: list[float],
) -> float | None:
    if not rr_values:
        return None

    artifacts = [
        value
        for value in rr_values
        if value < 300 or value > 2000
    ]
    return round(len(artifacts) / len(rr_values) * 100, 2)


def build_quality_warnings(
    *,
    samples_total: int,
    samples_synchronized: int,
    match_rate: float,
    has_hrv: bool,
    has_spo2: bool,
    sensor_mismatch: bool,
) -> list[str]:
    warnings = []

    if samples_total < 5:
        warnings.append("too_few_total_samples")

    if samples_synchronized < 5:
        warnings.append("too_few_synchronized_samples")

    if match_rate < 80:
        warnings.append("low_match_rate")

    if not has_hrv:
        warnings.append("missing_hrv_or_rr")

    if not has_spo2:
        warnings.append("missing_spo2")

    if sensor_mismatch:
        warnings.append("sensor_alignment_warning")

    return warnings


def calculate_data_quality_score(
    *,
    match_rate: float,
    quality_warnings: list[str],
) -> float:
    penalties = {
        "too_few_total_samples": 15,
        "too_few_synchronized_samples": 20,
        "low_match_rate": 15,
        "missing_hrv_or_rr": 15,
        "missing_spo2": 15,
        "sensor_alignment_warning": 10,
    }

    score = match_rate - sum(
        penalties.get(warning, 0)
        for warning in quality_warnings
    )
    return round(max(0, min(score, 100)), 2)


def build_research_summary(
    *,
    reasons: list[str],
    positive_findings: list[str],
    sensor_mismatch: bool,
    max_difference: float | None,
) -> str:
    """Build a readable research summary instead of a raw rule list."""

    sentences = []

    if positive_findings:
        sentences.append(
            ". ".join(positive_findings) + "."
        )

    if sensor_mismatch:
        detail = (
            f" The maximum observed difference was {max_difference:.1f} bpm."
            if max_difference is not None
            else ""
        )

        sentences.append(
            "A notable discrepancy was detected between wearable heart rate "
            "and pulse oximeter pulse, which may indicate sensor alignment, "
            f"time alignment issues, or signal artifact.{detail}"
        )

    other_reasons = [
        reason
        for reason in reasons
        if not reason.startswith(
            "Notable discrepancy between wearable heart rate"
        )
    ]

    if other_reasons:
        sentences.append(
            "Additional wellness findings: "
            + "; ".join(other_reasons)
            + "."
        )

    return " ".join(sentences)


def build_recommendations(
    *,
    anomaly_detected: bool,
    sensor_mismatch: bool,
    context_features: dict[str, Any] | None = None,
) -> str:
    """Return concise next-step guidance for the analysis card."""

    context_features = context_features or {}

    if sensor_mismatch:
        return (
            "Review the synchronized timeline, sensor placement, and time "
            "alignment before interpreting HR/pulse trends."
        )

    if context_features.get("poor_sleep"):
        return (
            "Sleep context suggests reduced recovery readiness. Consider an "
            "easier day and compare tomorrow's HRV/resting response."
        )

    if context_features.get("high_training_load"):
        return (
            "Recent training load may influence HR/HRV response. Treat this "
            "session as recovery support and watch the next baseline reading."
        )

    if context_features.get("high_stress_or_fatigue"):
        return (
            "Reported stress or fatigue is elevated. Prioritize recovery and "
            "repeat measurement under calmer conditions."
        )

    if anomaly_detected:
        return "Review the synchronized timeline, raw signals, and recovery context."

    return "No additional wellness action indicated."


def load_session_context(
    cursor,
    *,
    session_id: str,
) -> dict[str, Any]:
    """Load optional PRE/POST questionnaire context for AI coaching."""

    cursor.execute(
        """
        SELECT pre_json, post_json
        FROM full_sessions
        WHERE session_id = %s
        LIMIT 1
        """,
        (session_id,),
    )

    row = cursor.fetchone()

    if not row:
        return {}

    pre = decode_json(row[0])
    post = decode_json(row[1])

    return {
        "pre_check_in": pre.get("check_in") or {},
        "post_check_out": post.get("check_out") or {},
    }


def summarize_session_context(context: dict[str, Any]) -> dict[str, Any]:
    """Convert subjective check-in data into coaching-friendly flags."""

    pre = context.get("pre_check_in") or {}
    post = context.get("post_check_out") or {}
    sleep_hours = pre.get("sleep_hours")

    poor_sleep = (
        pre.get("sleep_quality") == "poor"
        or (
            isinstance(sleep_hours, (int, float))
            and sleep_hours < 6
        )
    )
    high_training_load = pre.get("training_load_24h") == "hard"
    high_stress_or_fatigue = (
        pre.get("stress_level") == "high"
        or pre.get("fatigue_level") == "high"
    )

    positive_subjective_response = (
        post.get("energy_level") == "higher"
        or post.get("relaxation_level") == "high"
        or post.get("fatigue_level") == "lower"
    )

    discomfort_reported = post.get("discomfort") in {
        "mild",
        "moderate",
    }

    return {
        "has_daily_context": bool(
            any(value not in (None, "") for value in pre.values())
            or any(value not in (None, "") for value in post.values())
        ),
        "poor_sleep": poor_sleep,
        "high_training_load": high_training_load,
        "high_stress_or_fatigue": high_stress_or_fatigue,
        "positive_subjective_response": positive_subjective_response,
        "discomfort_reported": discomfort_reported,
    }


def decode_json(value: Any) -> dict[str, Any]:
    """Return dict JSON payloads regardless of database adapter decoding."""

    if isinstance(value, dict):
        return value

    if not value:
        return {}

    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        return {}

    return decoded if isinstance(decoded, dict) else {}


def serialize_timeline_row(row: dict[str, Any]) -> dict[str, Any]:
    """Convert merged rows to JSON-friendly timeline points."""

    timestamp = row.get("timestamp")

    return {
        "timestamp": (
            timestamp.isoformat()
            if hasattr(timestamp, "isoformat")
            else timestamp
        ),
        "heart_rate": row.get("heart_rate"),
        "pulse": row.get("pulse"),
        "spo2": row.get("spo2"),
        "hrv": row.get("hrv"),
        "rr_interval": row.get("rr_interval"),
        "synchronized": row.get("synchronized"),
    }


def average(values: list[float]) -> float | None:
    """Return rounded mean or None for empty input."""

    return (
        round(mean(values), 2)
        if values
        else None
    )


def minimum(values: list[float]) -> float | None:
    """Return minimum or None for empty input."""

    return min(values) if values else None


def maximum(values: list[float]) -> float | None:
    """Return maximum or None for empty input."""

    return max(values) if values else None
