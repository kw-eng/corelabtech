"""Rule-based physiology analysis for merged HBOT telemetry.

The service reads synchronized FIT/CSV measurements, computes quality and
physiology signals, and persists an AI-style result for dashboards/reports.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import mean
from typing import Any

from database_postgres import db

from repositories.analysis_repository import (
    complete_ai_result,
    create_ai_result,
)

from repositories.merge_repository import (
    get_latest_completed_merge_job,
    load_merged_measurements,
)


MODEL_NAME = "CoreLabTech Physiology Analysis"
MODEL_VERSION = "rules-v1"


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

        result = analyze_measurements(
            measurements=measurements,
            usable=usable,
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
) -> dict[str, Any]:
    """Calculate scores and warnings from synchronized measurements.

    The model is intentionally deterministic and research-only: it applies
    thresholds for hypoxia, stress, cardiovascular warnings and sensor mismatch.
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
            "SpO2 dropped below 90%"
        )
    elif min_spo2 is not None and min_spo2 < 94:
        score -= 15
        reasons.append(
            "SpO2 was below 94%"
        )
    else:
        positive_findings.append(
            "SpO2 remained stable and within the expected range"
        )

    if stress_detected:
        score -= 20
        reasons.append(
            "Average HRV was below 30 ms"
        )

    if cardiovascular_warning:
        score -= 15
        reasons.append(
            "Heart rate exceeded 160 bpm"
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

    data_quality_score = match_rate

    features = {
        "samples_total": len(measurements),
        "samples_synchronized": len(usable),
        "match_rate": match_rate,

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

        "avg_hr_pulse_difference": average(
            differences
        ),
        "max_hr_pulse_difference": max_difference,
    }

    anomaly_detected = bool(
        hypoxia_detected
        or stress_detected
        or cardiovascular_warning
        or sensor_mismatch
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
        "medical_disclaimer": (
            "Research-only result. "
            "Not a medical diagnosis."
        ),
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
            "and pulse oximeter pulse, which may indicate sensor mismatch, "
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
            "Additional rule-based findings: "
            + "; ".join(other_reasons)
            + "."
        )

    return " ".join(sentences)


def build_recommendations(
    *,
    anomaly_detected: bool,
    sensor_mismatch: bool,
) -> str:
    """Return concise next-step guidance for the analysis card."""

    if sensor_mismatch:
        return (
            "Review the synchronized timeline, sensor placement, and time "
            "alignment before interpreting HR/pulse trends."
        )

    if anomaly_detected:
        return "Review synchronized timeline and raw signals."

    return "No additional research action indicated."


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
