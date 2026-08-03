"""Telemetry capability scanner.

This module inspects normalized telemetry records and determines:

- which physiological signals are available,
- how many valid samples exist,
- source time coverage,
- telemetry quality,
- which analyses can be performed.

The scanner is independent of device brand and model.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from typing import Any

from core.telemetry.analysis_availability import (
    determine_analysis_availability,
)
from core.telemetry.quality_engine import (
    assess_telemetry_quality,
    extract_row_rr_values,
    first_numeric,
    first_present,
    parse_timestamp,
)


CAPABILITY_SCHEMA_VERSION = "telemetry-capabilities-v2"

TIMESTAMP_FIELDS = (
    "timestamp_utc",
    "timestamp",
    "time",
    "original_timestamp",
)

HEART_RATE_FIELDS = (
    "heart_rate",
    "heart_rate_bpm",
    "hr",
)

PULSE_FIELDS = (
    "pulse",
    "pulse_rate_bpm",
)

SPO2_FIELDS = (
    "spo2",
    "oxygen_saturation",
)

HRV_FIELDS = (
    "hrv",
    "rmssd",
)

MOTION_FIELDS = (
    "motion",
    "cadence",
    "accelerometer",
)

TEMPERATURE_FIELDS = (
    "temperature",
    "body_temperature",
    "skin_temperature",
    "chamber_temperature",
)

RESPIRATION_FIELDS = (
    "respiration_rate",
    "respiratory_rate",
    "breathing_rate",
)

PRESSURE_FIELDS = (
    "pressure",
    "pressure_ata",
    "actual_ata",
)

SESSION_MARKER_FIELDS = (
    "phase",
    "session_phase",
    "event",
    "event_type",
)


def scan_telemetry_capabilities(
    rows: Iterable[Mapping[str, Any]],
    *,
    file_type: str | None = None,
    source_type: str | None = None,
    expected_signals: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Build a complete Telemetry Intelligence report.

    The function examines actual record contents. It does not determine
    compatibility from device manufacturer or model.

    Args:
        rows:
            Normalized telemetry records.
        file_type:
            Optional file format, for example FIT, CSV, JSON or XML.
        source_type:
            Optional generic source category. When omitted, it is inferred
            from detected signals.
        expected_signals:
            Optional list of signals expected from this source. Missing
            expected signals can reduce the data-quality score.

    Returns:
        JSON-serializable capability report containing:

        - file metadata,
        - detected signals,
        - sample counts,
        - data-quality assessment,
        - analysis availability.
    """

    normalized_rows = normalize_rows(rows)
    record_count = len(normalized_rows)

    timestamps = collect_timestamps(normalized_rows)

    sample_counts = {
        "records": record_count,
        "timestamps": count_timestamps(normalized_rows),
        "heart_rate": count_numeric_signal(
            normalized_rows,
            HEART_RATE_FIELDS,
        ),
        "pulse": count_numeric_signal(
            normalized_rows,
            PULSE_FIELDS,
        ),
        "rr_intervals": count_rr_samples(normalized_rows),
        "rr_records": count_rr_records(normalized_rows),
        "reported_hrv": count_numeric_signal(
            normalized_rows,
            HRV_FIELDS,
        ),
        "spo2": count_numeric_signal(
            normalized_rows,
            SPO2_FIELDS,
        ),
        "motion": count_numeric_signal(
            normalized_rows,
            MOTION_FIELDS,
        ),
        "temperature": count_numeric_signal(
            normalized_rows,
            TEMPERATURE_FIELDS,
        ),
        "respiration": count_numeric_signal(
            normalized_rows,
            RESPIRATION_FIELDS,
        ),
        "pressure": count_numeric_signal(
            normalized_rows,
            PRESSURE_FIELDS,
        ),
        "session_markers": count_nonempty_signal(
            normalized_rows,
            SESSION_MARKER_FIELDS,
        ),
    }

    signals = {
        "timestamp": sample_counts["timestamps"] > 0,
        "heart_rate": sample_counts["heart_rate"] > 0,
        "pulse": sample_counts["pulse"] > 0,
        "rr_intervals": sample_counts["rr_intervals"] > 0,
        "reported_hrv": sample_counts["reported_hrv"] > 0,
        "hrv": (
            sample_counts["rr_intervals"] > 0
            or sample_counts["reported_hrv"] > 0
        ),
        "spo2": sample_counts["spo2"] > 0,
        "motion": sample_counts["motion"] > 0,
        "temperature": sample_counts["temperature"] > 0,
        "respiration": sample_counts["respiration"] > 0,
        "pressure": sample_counts["pressure"] > 0,
        "session_markers": sample_counts["session_markers"] > 0,
    }

    resolved_source_type = (
        normalize_source_type(source_type)
        or infer_source_type(signals)
    )

    quality_details = assess_telemetry_quality(
        normalized_rows,
        expected_signals=expected_signals,
    )

    quality_summary = build_quality_summary(
        quality_details
    )

    file_report = build_file_report(
        file_type=file_type,
        source_type=resolved_source_type,
        record_count=record_count,
        timestamps=timestamps,
    )

    capability_report: dict[str, Any] = {
        "schema_version": CAPABILITY_SCHEMA_VERSION,
        "file": file_report,
        "signals": signals,
        "detected_signals": [
            signal_name
            for signal_name, available in signals.items()
            if available
        ],
        "sample_counts": sample_counts,
        "quality": quality_summary,
        "technical": {
            "file_type": normalize_file_type(file_type),
            "source_type": resolved_source_type,
            "expected_signals": list(
                expected_signals or []
            ),
        },
    }

    capability_report["analysis"] = (
        determine_analysis_availability(
            capability_report
        )
    )

    return capability_report


def normalize_rows(
    rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Convert valid mapping records to mutable dictionaries."""

    if rows is None:
        return []

    return [
        dict(row)
        for row in rows
        if isinstance(row, Mapping)
    ]


def collect_timestamps(
    rows: Sequence[Mapping[str, Any]],
) -> list[datetime]:
    """Return parsed timestamps sorted chronologically."""

    timestamps: list[datetime] = []

    for row in rows:
        timestamp = parse_timestamp(
            first_present(
                row,
                TIMESTAMP_FIELDS,
            )
        )

        if timestamp is not None:
            timestamps.append(timestamp)

    try:
        return sorted(timestamps)
    except TypeError:
        # Mixed timezone-aware and naive datetimes cannot be compared.
        return timestamps


def count_timestamps(
    rows: Sequence[Mapping[str, Any]],
) -> int:
    """Count records containing a valid timestamp."""

    count = 0

    for row in rows:
        timestamp = parse_timestamp(
            first_present(
                row,
                TIMESTAMP_FIELDS,
            )
        )

        if timestamp is not None:
            count += 1

    return count


def count_numeric_signal(
    rows: Sequence[Mapping[str, Any]],
    fields: Sequence[str],
) -> int:
    """Count records containing at least one numeric signal value."""

    return sum(
        1
        for row in rows
        if first_numeric(row, fields) is not None
    )


def count_nonempty_signal(
    rows: Sequence[Mapping[str, Any]],
    fields: Sequence[str],
) -> int:
    """Count records containing a non-empty value."""

    return sum(
        1
        for row in rows
        if first_present(row, fields) is not None
    )


def count_rr_records(
    rows: Sequence[Mapping[str, Any]],
) -> int:
    """Count records containing at least one RR interval."""

    return sum(
        1
        for row in rows
        if extract_row_rr_values(row)
    )


def count_rr_samples(
    rows: Sequence[Mapping[str, Any]],
) -> int:
    """Count all RR samples, including packet values."""

    return sum(
        len(extract_row_rr_values(row))
        for row in rows
    )


def build_file_report(
    *,
    file_type: str | None,
    source_type: str,
    record_count: int,
    timestamps: Sequence[datetime],
) -> dict[str, Any]:
    """Build generic file and timeline metadata."""

    first_timestamp = (
        timestamps[0]
        if timestamps
        else None
    )

    last_timestamp = (
        timestamps[-1]
        if timestamps
        else None
    )

    coverage_seconds = calculate_coverage_seconds(
        timestamps
    )

    return {
        "type": normalize_file_type(file_type),
        "source_type": source_type,
        "records": record_count,
        "first_timestamp": (
            first_timestamp.isoformat()
            if first_timestamp is not None
            else None
        ),
        "last_timestamp": (
            last_timestamp.isoformat()
            if last_timestamp is not None
            else None
        ),
        "coverage_seconds": round(
            coverage_seconds,
            3,
        ),
        "coverage_minutes": round(
            coverage_seconds / 60,
            3,
        ),
    }


def build_quality_summary(
    quality_details: Mapping[str, Any],
) -> dict[str, Any]:
    """Flatten important quality values for the frontend.

    The complete quality-engine result remains available under ``details``.
    """

    timestamp_quality = as_mapping(
        quality_details.get("timestamp")
    )
    rr_quality = as_mapping(
        quality_details.get("rr")
    )
    signal_quality = as_mapping(
        quality_details.get("signals")
    )

    return {
        "score": quality_details.get("score", 0),
        "level": quality_details.get(
            "level",
            "not_available",
        ),
        "records_total": quality_details.get(
            "records_total",
            0,
        ),
        "records_with_timestamp": timestamp_quality.get(
            "records_with_timestamp",
            0,
        ),
        "missing_timestamp_count": timestamp_quality.get(
            "missing_timestamp_count",
            0,
        ),
        "invalid_timestamp_count": timestamp_quality.get(
            "invalid_timestamp_count",
            0,
        ),
        "timestamp_completeness_percent": timestamp_quality.get(
            "completeness_percent",
            0,
        ),
        "heart_rate_completeness_percent": get_signal_completeness(
            signal_quality,
            "heart_rate",
        ),
        "pulse_completeness_percent": get_signal_completeness(
            signal_quality,
            "pulse",
        ),
        "spo2_completeness_percent": get_signal_completeness(
            signal_quality,
            "spo2",
        ),
        "rr_valid_count": rr_quality.get(
            "samples_valid",
            0,
        ),
        "rr_invalid_count": rr_quality.get(
            "samples_invalid",
            0,
        ),
        "rr_artifact_count": rr_quality.get(
            "artifacts_detected",
            0,
        ),
        "rr_valid_percent": rr_quality.get(
            "valid_percent",
            0,
        ),
        "rr_artifact_percent": rr_quality.get(
            "artifact_percent",
            0,
        ),
        "gaps_detected": timestamp_quality.get(
            "gaps_detected",
            0,
        ),
        "largest_gap_seconds": timestamp_quality.get(
            "largest_gap_seconds",
            0,
        ),
        "typical_interval_seconds": timestamp_quality.get(
            "typical_interval_seconds"
        ),
        "sampling_frequency_hz": timestamp_quality.get(
            "sampling_frequency_hz"
        ),
        "warnings": list(
            quality_details.get("warnings") or []
        ),
        "is_usable": bool(
            quality_details.get("is_usable")
        ),
        "is_reliable": bool(
            quality_details.get("is_reliable")
        ),
        "is_high_quality": bool(
            quality_details.get("is_high_quality")
        ),
        "details": dict(quality_details),
    }


def get_signal_completeness(
    signal_quality: Mapping[str, Any],
    signal_name: str,
) -> float:
    """Read one completeness percentage from the quality report."""

    completeness = as_mapping(
        signal_quality.get(
            "completeness_percent"
        )
    )

    value = completeness.get(signal_name)

    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return 0.0


def infer_source_type(
    signals: Mapping[str, bool],
) -> str:
    """Infer a generic source category from detected capabilities."""

    has_rr_or_hr = bool(
        signals.get("rr_intervals")
        or signals.get("heart_rate")
        or signals.get("reported_hrv")
    )

    has_oxygen = bool(
        signals.get("spo2")
        or signals.get("pulse")
    )

    has_session_context = bool(
        signals.get("pressure")
        or signals.get("session_markers")
    )

    if has_rr_or_hr and has_oxygen:
        return "combined_physiological_telemetry"

    if has_rr_or_hr:
        return "wearable_telemetry"

    if has_oxygen:
        return "pulse_oximetry"

    if has_session_context:
        return "session_telemetry"

    return "external_telemetry"


def normalize_file_type(
    file_type: str | None,
) -> str | None:
    """Normalize a source file type for API presentation."""

    if not file_type:
        return None

    normalized = str(file_type).strip().upper()

    return normalized or None


def normalize_source_type(
    source_type: str | None,
) -> str | None:
    """Normalize generic source category."""

    if not source_type:
        return None

    normalized = (
        str(source_type)
        .strip()
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
    )

    return normalized or None


def calculate_coverage_seconds(
    timestamps: Sequence[datetime],
) -> float:
    """Calculate timeline coverage between first and last timestamp."""

    if len(timestamps) < 2:
        return 0.0

    try:
        return max(
            (
                timestamps[-1]
                - timestamps[0]
            ).total_seconds(),
            0.0,
        )
    except TypeError:
        return 0.0


def as_mapping(
    value: Any,
) -> Mapping[str, Any]:
    """Return a mapping or an empty mapping."""

    if isinstance(value, Mapping):
        return value

    return {}