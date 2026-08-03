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
from services.hrv_pipeline import (
    DEFAULT_HRV_WINDOW_SECONDS,
    calculate_hrv_from_rr,
    calculate_hrv_phase_metrics,
    calculate_hrv_windows,
)
from services.telemetry_quality import (
    SENSOR_MISMATCH_THRESHOLD_BPM,
    assess_telemetry_quality,
)
from services.llm_narration import (
    FACT_SHEET_VERSION,
    NARRATION_VERSION,
    build_session_fact_sheet,
    narrate_fact_sheet,
    narration_instructions,
)
from services.insight_views import (
    build_operator_report,
    build_recovery_coach,
    build_session_comparison,
    build_session_summary,
    session_quality_label,
)

from repositories.analysis_repository import (
    complete_ai_result,
    create_ai_result,
)

from repositories.merge_repository import (
    get_latest_completed_merge_job,
    load_merged_measurements,
)
from repositories.wellness_repository import (
    get_wellness_summary,
    refresh_daily_baseline,
    upsert_session_features,
)
from repositories.recovery_repository import (
    load_latest_recovery_follow_ups,
    load_recovery_follow_up_history,
)


MODEL_NAME = "CoreLabTech Wellness Session Analysis"
MODEL_VERSION = "wellness-rules-v2"
WELLNESS_DISCLAIMER = (
    "Wellness and educational insight only. "
    "Not intended to diagnose, treat, cure, or prevent disease."
)


def get_analysis_model_manifest() -> dict[str, Any]:
    """Return the admin-facing, versioned description of the active rules."""

    result = {
        "name": MODEL_NAME,
        "version": MODEL_VERSION,
        "mode": "Deterministic wellness rules",
        "hrv_algorithm_version": "rr-clean-v2",
        "layers": [
            {
                "title": "Signals and provenance",
                "items": [
                    "Chest HRM/ECG is the reference for heart rate and RR.",
                    "Pulse oximeter is the reference for SpO2; its PPG pulse is auxiliary.",
                    "Unknown and wearable PPG sources remain trend-only.",
                ],
            },
            {
                "title": "Data-quality gate",
                "items": [
                    "UTC-aware nearest-timestamp merge with a configured tolerance.",
                    "Coverage, temporal coverage, HR-PPG agreement and sustained divergence affect confidence.",
                    "Sensor disagreement does not reduce the wellness score or flag a physiological anomaly by itself.",
                ],
            },
            {
                "title": "Versioned HRV",
                "items": [
                    "RR is accepted only from chest_hrm/ecg sources.",
                    "Artifact filter: 300-2000 ms with delta and ratio checks.",
                    "RMSSD, SDNN and pNN50 are calculated for the session, 60-second windows and configured phases.",
                ],
            },
            {
                "title": "Wellness scoring",
                "items": [
                    "Score starts at 100; low SpO2, validated low HRV and high heart rate can reduce it.",
                    "HRV is not scored without sufficient approved RR.",
                    "analysis_confidence is reported separately from the wellness score.",
                ],
            },
        ],
        "guardrails": [
            "Wellness and educational use only; no diagnosis, treatment or disease claim.",
            "Device-reported HRV cannot replace raw approved RR intervals.",
            "Historical data with unknown provenance remains explicitly unknown.",
        ],
        "llm_narration": {
            "version": NARRATION_VERSION,
            "fact_sheet_version": FACT_SHEET_VERSION,
            "summary": (
                "Optional LLM layer receives only the versioned fact sheet "
                "after deterministic analysis."
            ),
            "instructions": narration_instructions(),
        },
    }

    return result


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

        session_client_id = load_session_client_id(
            cursor,
            session_id=session_id,
        )
        final_user_id = (
            session_client_id
            or merge_job.get("user_id")
            or user_id
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
        result["client_id"] = final_user_id
        result["model_name"] = MODEL_NAME
        result["model_version"] = MODEL_VERSION
        result["protocol"] = session_context.get("protocol") or {}
        result["chamber"] = session_context.get("chamber") or {}

        ai_result_id = create_ai_result(
            cursor,
            merge_id=merge_job["merge_id"],
            session_id=session_id,
            user_id=final_user_id,
            model_name=MODEL_NAME,
            model_version=MODEL_VERSION,
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
            protocol_id=session_context["protocol_id"],
            target_ata=session_context.get("target_ata"),
            actual_ata=session_context.get("actual_ata"),
        )

        result["wellness_history"] = get_wellness_summary(
            cursor,
            user_id=final_user_id,
            protocol_id=session_context["protocol_id"],
            limit=30,
        )
        result["operator_report"] = build_operator_report(result)
        result["session_quality"] = {
            "label": session_quality_label(result.get("data_quality_score")),
            "data_quality_score": result.get("data_quality_score"),
        }
        result["session_comparison"] = build_session_comparison(
            result["wellness_history"]
        )
        result["recovery_coach"] = build_recovery_coach(
            analysis=result,
            follow_ups=session_context.get("recovery_follow_ups"),
            check_in=session_context.get("pre_check_in"),
            personal_history=load_recovery_follow_up_history(
                cursor,
                user_id=final_user_id,
                exclude_session_id=session_id,
            ),
        )
        attach_narration(result)

        complete_ai_result(
            cursor,
            ai_result_id=ai_result_id,
            result=result,
        )

        refresh_daily_baseline(
            cursor,
            user_id=final_user_id,
            protocol_id=session_context["protocol_id"],
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

    session_context = session_context or {}

    spo2_values = numeric_values(
        usable,
        "spo2",
    )

    hr_values = numeric_values(
        usable,
        "heart_rate_bpm",
    )

    if not hr_values:
        hr_values = numeric_values(usable, "heart_rate")

    reference_hr_rows = [
        row for row in usable
        if row.get("hr_source_type") == "chest_hrm"
        and row.get("hr_measurement_method") == "ecg"
    ]
    reference_hr_values = numeric_values(
        reference_hr_rows,
        "heart_rate_bpm",
    ) or numeric_values(reference_hr_rows, "heart_rate")

    pulse_values = numeric_values(
        usable,
        "pulse_rate_bpm",
    )

    if not pulse_values:
        pulse_values = numeric_values(usable, "pulse")

    reported_hrv_values = numeric_values(
        usable,
        "hrv",
    )

    min_spo2 = minimum(spo2_values)
    hrv_metrics = calculate_hrv_from_rr(usable)
    hrv_windows = calculate_hrv_windows(
        usable,
        session_segments=session_context.get("segments"),
    )
    hrv_phase_metrics = calculate_hrv_phase_metrics(
        usable,
        session_segments=session_context.get("segments"),
    )
    avg_hrv = hrv_metrics["rmssd"]
    max_hr = maximum(hr_values)
    max_reference_hr = maximum(reference_hr_values)
    rr_values = numeric_values(usable, "rr_interval")
    window_start = first_timestamp(usable)
    window_end = last_timestamp(usable)
    time_alignment_quality = source_summary(
        usable, "time_alignment_quality"
    )
    telemetry_quality = assess_telemetry_quality(
        measurements=measurements,
        usable=usable,
        time_alignment_quality=time_alignment_quality,
    )
    max_difference = telemetry_quality["max_hr_pulse_difference_bpm"]

    hypoxia_detected = (
        min_spo2 is not None
        and min_spo2 < 90
    )

    stress_detected = (
        avg_hrv is not None
        and hrv_metrics["hrv_usable_for_scoring"]
        and avg_hrv < 30
    )

    cardiovascular_warning = (
        max_reference_hr is not None
        and max_reference_hr > 160
    )

    sensor_mismatch = (
        max_difference is not None
        and max_difference > SENSOR_MISMATCH_THRESHOLD_BPM
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

    score = max(0, min(score, 100))

    match_rate = round(
        len(usable) / len(measurements) * 100,
        2,
    )

    quality_warnings = build_quality_warnings(
        samples_total=len(measurements),
        samples_synchronized=len(usable),
        match_rate=match_rate,
        has_hrv=bool(hrv_metrics["rr_count"]),
        has_spo2=bool(spo2_values),
        sensor_mismatch=sensor_mismatch,
    )

    quality_warnings.extend(telemetry_quality["quality_reasons"])

    hr_source_type = source_summary(usable, "hr_source_type")
    if hr_values and hr_source_type == "unknown":
        quality_warnings.append("heart_rate_source_unknown")
    if hrv_metrics["hrv_confidence"] in {"low", "unavailable"}:
        quality_warnings.append("insufficient_rr_for_hrv")
    if hrv_metrics["rr_source_rejected_count"]:
        quality_warnings.append("unapproved_rr_source")

    data_quality_score = calculate_data_quality_score(
        match_rate=match_rate,
        quality_warnings=quality_warnings,
    )

    context_features = summarize_session_context(session_context)

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
        "avg_reference_heart_rate": average(reference_hr_values),
        "max_reference_heart_rate": max_reference_hr,

        "avg_pulse": average(pulse_values),
        "min_pulse": minimum(pulse_values),
        "max_pulse": maximum(pulse_values),

        "avg_hrv": avg_hrv,
        "min_hrv": None,
        "max_hrv": None,
        "device_reported_hrv": average(reported_hrv_values),
        **hrv_metrics,
        "hrv_window_seconds": DEFAULT_HRV_WINDOW_SECONDS,
        "hrv_windows": hrv_windows,
        "hrv_phase_metrics": hrv_phase_metrics,

        "avg_hr_pulse_difference": telemetry_quality[
            "median_hr_pulse_difference_bpm"
        ],
        **telemetry_quality,
        "max_hr_pulse_difference": max_difference,
        "hr_source_type": source_summary(usable, "hr_source_type"),
        "hr_measurement_method": source_summary(
            usable, "hr_measurement_method"
        ),
        "pulse_source_type": source_summary(
            usable, "pulse_source_type"
        ),
        "pulse_measurement_method": source_summary(
            usable, "pulse_measurement_method"
        ),
        "time_alignment_method": source_summary(
            usable, "time_alignment_method"
        ),
        "time_alignment_quality": time_alignment_quality,
        "session_context": session_context,
        "context_features": context_features,
    }

    anomaly_detected = bool(
        hypoxia_detected
        or stress_detected
        or cardiovascular_warning
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
        features=features,
        context_features=context_features,
    )

    recommendations = build_recommendations(
        anomaly_detected=anomaly_detected,
        sensor_mismatch=sensor_mismatch,
        context_features=context_features,
    )

    result = {
        "overall_score": score,
        "wellness_response_score": score,
        "score_type": "Wellness Response",
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
        "analysis_confidence": calculate_analysis_confidence(
            data_quality_score=data_quality_score,
            has_reference_hr=hr_source_type == "chest_hrm",
            has_rr=hrv_metrics["hrv_usable_for_scoring"],
            time_alignment_quality=time_alignment_quality,
            signal_quality=telemetry_quality["signal_quality"],
        ),

        "anomaly_detected": anomaly_detected,
        "stress_detected": stress_detected,
        "hypoxia_detected": hypoxia_detected,
        "arrhythmia_detected": False,

        "product_mode": "wellness",
        "wellness_only": True,
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
        "session_context": session_context,
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

    return result


def attach_narration(result: dict[str, Any]) -> None:
    """Attach the optional LLM narrative after all deterministic facts exist."""

    deterministic_summary = result["summary"]
    fact_sheet = build_session_fact_sheet(result)
    narration = narrate_fact_sheet(fact_sheet)
    result["deterministic_summary"] = deterministic_summary
    result["narration"] = {
        **narration.to_dict(),
        "fact_sheet": fact_sheet,
    }
    result["session_summary"] = build_session_summary(
        analysis=result,
        narration=result["narration"],
    )
    if narration.status == "generated":
        result["summary"] = narration.text


def load_session_client_id(
    cursor,
    *,
    session_id: str,
) -> str | None:
    """Resolve the canonical client from the completed session record."""

    cursor.execute(
        """
        SELECT user_id
        FROM full_sessions
        WHERE session_id = %s
        LIMIT 1
        """,
        (session_id,),
    )
    row = cursor.fetchone()
    return row[0] if row and row[0] else None


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


def first_not_none(*values: Any) -> Any:
    """Return the first available value without treating zero as missing."""

    for value in values:
        if value is not None:
            return value
    return None


def source_summary(rows: list[dict[str, Any]], key: str) -> str:
    """Summarize provenance without inventing a source for historical rows."""

    values = {
        str(row[key])
        for row in rows
        if row.get(key) not in (None, "", "unknown")
    }
    if not values:
        return "unknown"
    return values.pop() if len(values) == 1 else "mixed"


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
        "low_synchronized_coverage": 10,
        "low_synchronized_temporal_coverage": 10,
        "low_hr_pulse_agreement": 10,
        "sustained_hr_pulse_divergence": 10,
        "time_alignment_uncertain": 15,
        "heart_rate_source_unknown": 10,
        "insufficient_rr_for_hrv": 10,
        "unapproved_rr_source": 10,
    }

    score = match_rate - sum(
        penalties.get(warning, 0)
        for warning in quality_warnings
    )
    return round(max(0, min(score, 100)), 2)


def calculate_analysis_confidence(
    *,
    data_quality_score: float,
    has_reference_hr: bool,
    has_rr: bool,
    time_alignment_quality: str,
    signal_quality: str,
) -> str:
    """Grade interpretation confidence separately from wellness outcome."""

    if (
        data_quality_score >= 80
        and has_reference_hr
        and has_rr
        and time_alignment_quality == "high"
        and signal_quality == "high"
    ):
        return "high"
    if (
        data_quality_score >= 60
        and has_reference_hr
        and time_alignment_quality not in {"low", "unknown"}
        and signal_quality in {"medium", "high"}
    ):
        return "medium"
    return "low"


def build_research_summary(
    *,
    reasons: list[str],
    positive_findings: list[str],
    sensor_mismatch: bool,
    max_difference: float | None,
    features: dict[str, Any] | None = None,
    context_features: dict[str, Any] | None = None,
) -> str:
    """Build a readable research summary instead of a raw rule list."""

    features = features or {}
    context_features = context_features or {}
    sentences = []

    if positive_findings:
        sentences.append(
            ". ".join(positive_findings) + "."
        )

    physiology_sentence = build_physiology_summary_sentence(features)
    if physiology_sentence:
        sentences.append(physiology_sentence)

    context_sentence = build_context_summary_sentence(context_features)
    if context_sentence:
        sentences.append(context_sentence)

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


def build_physiology_summary_sentence(features: dict[str, Any]) -> str:
    """Summarize pulse, HR and HRV without turning them into diagnosis."""

    parts = []
    avg_pulse = features.get("avg_pulse")
    min_pulse = features.get("min_pulse")
    max_pulse = features.get("max_pulse")
    avg_hr = features.get("avg_heart_rate")
    min_hr = features.get("min_heart_rate")
    max_hr = features.get("max_heart_rate")
    avg_hrv = features.get("avg_hrv")

    if avg_pulse is not None:
        pulse_text = f"Pulse averaged {format_summary_number(avg_pulse, 0)} bpm"
        if min_pulse is not None and max_pulse is not None:
            pulse_text += (
                f" (range {format_summary_number(min_pulse, 0)}-"
                f"{format_summary_number(max_pulse, 0)} bpm)"
            )
        parts.append(pulse_text)

    if avg_hr is not None:
        hr_text = f"wearable HR averaged {format_summary_number(avg_hr, 0)} bpm"
        if min_hr is not None and max_hr is not None:
            hr_text += (
                f" (range {format_summary_number(min_hr, 0)}-"
                f"{format_summary_number(max_hr, 0)} bpm)"
            )
        parts.append(hr_text)

    if avg_hrv is not None:
        parts.append(
            f"average HRV was {format_summary_number(avg_hrv, 1)} ms"
        )

    if not parts:
        return ""

    return (
        "Pulse, wearable HR and HRV should be interpreted as wellness trend "
        f"signals: {'; '.join(parts)}."
    )


def build_context_summary_sentence(context_features: dict[str, Any]) -> str:
    """Connect check-in context to interpretation without overstating causality."""

    notes = []

    if context_features.get("poor_sleep"):
        notes.append("reduced sleep quality or short sleep")

    if context_features.get("high_training_load"):
        notes.append("higher recent activity load")

    if context_features.get("high_stress_or_fatigue"):
        notes.append("reported stress or fatigue")

    if context_features.get("recovery_improved"):
        notes.append("post-session recovery feedback improved")

    if not notes:
        return (
            "No elevated sleep, fatigue, stress or recent activity context was "
            "flagged in the available check-in data."
        )

    return (
        "Check-in context may influence today’s physiology interpretation: "
        + ", ".join(notes)
        + "."
    )


def format_summary_number(value: Any, digits: int = 1) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)

    if digits == 0:
        return str(int(round(numeric)))

    return f"{numeric:.{digits}f}".rstrip("0").rstrip(".")


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
        SELECT
            fs.pre_json,
            fs.during_json,
            fs.post_json,
            fs.protocol_id,
            fs.chamber_id,
            fs.target_ata,
            fs.actual_ata,
            fs.pressure_input_value,
            fs.pressure_input_unit,
            fs.pressure_deviation,
            p.code,
            p.name,
            p.mode,
            p.planned_duration_min,
            c.code,
            c.name,
            c.location,
            fs.compression_time_min,
            fs.exposure_time_min,
            fs.decompression_time_min,
            fs.total_duration_min,
            fs.execution_status,
            fs.deviation_reason,
            fs.program_enrollment_id,
            fs.protocol_version
        FROM full_sessions fs
        LEFT JOIN protocols p
            ON p.protocol_id = fs.protocol_id
        LEFT JOIN chambers c
            ON c.chamber_id = fs.chamber_id
        WHERE fs.session_id = %s
        LIMIT 1
        """,
        (session_id,),
    )

    row = cursor.fetchone()

    if not row:
        return {}

    pre = decode_json(row[0])
    during = decode_json(row[1])
    post = decode_json(row[2])

    context = {
        "pre_check_in": pre.get("check_in") or {},
        "post_check_out": post.get("check_out") or {},
        "during": during,
        "protocol_id": row[3],
        "chamber_id": row[4],
        "target_ata": row[5],
        "actual_ata": row[6],
        "pressure_input_value": row[7],
        "pressure_input_unit": row[8],
        "pressure_deviation": row[9],
        "session_timing": {
            "compression_time_min": row[17],
            "exposure_time_min": row[18],
            "decompression_time_min": row[19],
            "total_duration_min": row[20],
        },
        "execution_status": row[21],
        "deviation_reason": row[22],
        "program_enrollment_id": row[23],
        "protocol": {
            "protocol_id": row[3],
            "code": row[10],
            "name": row[11],
            "mode": row[12],
            "planned_duration_min": row[13],
            "target_ata": row[5],
            "version": row[24],
        },
        "chamber": {
            "chamber_id": row[4],
            "code": row[14],
            "name": row[15],
            "location": row[16],
        },
    }
    cursor.execute(
        """
        SELECT
            sequence_no,
            phase,
            actual_duration_min,
            target_ata,
            actual_ata,
            oxygen_mode,
            note
        FROM session_segments
        WHERE session_id = %s
        ORDER BY sequence_no
        """,
        (session_id,),
    )
    context["segments"] = [
        {
            "sequence_no": segment[0],
            "phase": segment[1],
            "actual_duration_min": segment[2],
            "target_ata": segment[3],
            "actual_ata": segment[4],
            "oxygen_mode": segment[5],
            "note": segment[6],
        }
        for segment in cursor.fetchall()
    ]
    follow_ups = load_latest_recovery_follow_ups(cursor, session_id=session_id)
    context["recovery_follow_ups"] = follow_ups
    # Kept for fact sheets generated before recovery-coach-v2.
    context["recovery_follow_up"] = max(
        follow_ups.values(),
        key=lambda entry: entry.get("recorded_at") or "",
        default=None,
    )
    return context


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
        "heart_rate_bpm": first_not_none(
            row.get("heart_rate_bpm"), row.get("heart_rate")
        ),
        "pulse": row.get("pulse"),
        "pulse_rate_bpm": first_not_none(
            row.get("pulse_rate_bpm"), row.get("pulse")
        ),
        "spo2": row.get("spo2"),
        "hrv": row.get("hrv"),
        "rr_interval": row.get("rr_interval"),
        "synchronized": row.get("synchronized"),
        "hr_source_type": row.get("hr_source_type") or "unknown",
        "pulse_source_type": row.get("pulse_source_type") or "unknown",
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
