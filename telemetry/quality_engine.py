"""Telemetry data-quality assessment.

This module evaluates normalized physiological telemetry independently
of device vendor or model.

It assesses:

- timestamp completeness and continuity,
- sampling interval stability,
- duplicate timestamps,
- signal completeness,
- RR interval validity and artifacts,
- physiological range violations,
- synchronization quality,
- overall telemetry quality score.

All returned structures are JSON serializable.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from statistics import median
from typing import Any


QUALITY_SCHEMA_VERSION = "telemetry-quality-v1"

RR_MIN_SECONDS = 0.3
RR_MAX_SECONDS = 2.0
RR_MAX_DELTA_SECONDS = 0.15
RR_MAX_DELTA_RATIO = 0.20

HEART_RATE_MIN_BPM = 25.0
HEART_RATE_MAX_BPM = 240.0

PULSE_MIN_BPM = 25.0
PULSE_MAX_BPM = 240.0

SPO2_MIN_PERCENT = 50.0
SPO2_MAX_PERCENT = 100.0

DEFAULT_GAP_MULTIPLIER = 5.0
DEFAULT_MINIMUM_GAP_SECONDS = 10.0

DEFAULT_MERGE_TOLERANCE_MS = 2500.0


def assess_telemetry_quality(
    rows: Iterable[Mapping[str, Any]],
    *,
    expected_signals: Sequence[str] | None = None,
    gap_multiplier: float = DEFAULT_GAP_MULTIPLIER,
    minimum_gap_seconds: float = DEFAULT_MINIMUM_GAP_SECONDS,
) -> dict[str, Any]:
    """Assess quality of one normalized telemetry timeline.

    The function operates on signal availability and values. It does not
    require device vendor or model information.

    Supported record fields include:

    - timestamp / timestamp_utc / time / original_timestamp
    - heart_rate / heart_rate_bpm / hr
    - pulse / pulse_rate_bpm
    - rr_interval / rr_intervals
    - hrv / rmssd
    - spo2 / oxygen_saturation
    - motion
    - pressure / pressure_ata / actual_ata

    Args:
        rows:
            Normalized telemetry records.
        expected_signals:
            Optional names of signals expected for this source.
            Missing expected signals reduce completeness scoring.
        gap_multiplier:
            A gap is detected when it exceeds the typical interval multiplied
            by this value.
        minimum_gap_seconds:
            Gaps shorter than this value are ignored, even if they exceed the
            sampling-interval multiplier.

    Returns:
        JSON-serializable quality report.
    """

    normalized_rows = [
        dict(row)
        for row in rows
        if isinstance(row, Mapping)
    ]

    total_records = len(normalized_rows)

    timestamp_result = assess_timestamp_quality(
        normalized_rows,
        gap_multiplier=gap_multiplier,
        minimum_gap_seconds=minimum_gap_seconds,
    )

    signal_result = assess_signal_quality(
        normalized_rows,
        expected_signals=expected_signals,
    )

    rr_result = assess_rr_quality(normalized_rows)

    physiological_result = assess_physiological_ranges(
        normalized_rows
    )

    score_components = calculate_quality_score_components(
        total_records=total_records,
        timestamp_quality=timestamp_result,
        signal_quality=signal_result,
        rr_quality=rr_result,
        physiological_quality=physiological_result,
    )

    overall_score = calculate_weighted_score(
        score_components
    )

    warnings = build_quality_warnings(
        total_records=total_records,
        timestamp_quality=timestamp_result,
        signal_quality=signal_result,
        rr_quality=rr_result,
        physiological_quality=physiological_result,
        overall_score=overall_score,
    )

    return {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "score": overall_score,
        "level": quality_level(overall_score),
        "records_total": total_records,
        "timestamp": timestamp_result,
        "signals": signal_result,
        "rr": rr_result,
        "physiological_ranges": physiological_result,
        "score_components": score_components,
        "warnings": warnings,
        "is_usable": overall_score >= 40,
        "is_reliable": overall_score >= 70,
        "is_high_quality": overall_score >= 85,
    }


def assess_timestamp_quality(
    rows: Sequence[Mapping[str, Any]],
    *,
    gap_multiplier: float = DEFAULT_GAP_MULTIPLIER,
    minimum_gap_seconds: float = DEFAULT_MINIMUM_GAP_SECONDS,
) -> dict[str, Any]:
    """Assess timestamp availability, ordering and continuity."""

    total_records = len(rows)

    timestamp_entries: list[tuple[int, datetime]] = []
    invalid_timestamp_count = 0

    for index, row in enumerate(rows):
        raw_timestamp = first_present(
            row,
            (
                "timestamp_utc",
                "timestamp",
                "time",
                "original_timestamp",
            ),
        )

        parsed_timestamp = parse_timestamp(raw_timestamp)

        if parsed_timestamp is not None:
            timestamp_entries.append(
                (index, parsed_timestamp)
            )
        elif raw_timestamp not in (None, ""):
            invalid_timestamp_count += 1

    timestamp_count = len(timestamp_entries)
    missing_timestamp_count = max(
        total_records - timestamp_count,
        0,
    )

    completeness_percent = percentage(
        timestamp_count,
        total_records,
    )

    if not timestamp_entries:
        return {
            "available": False,
            "records_with_timestamp": 0,
            "missing_timestamp_count": missing_timestamp_count,
            "invalid_timestamp_count": invalid_timestamp_count,
            "completeness_percent": completeness_percent,
            "first_timestamp": None,
            "last_timestamp": None,
            "coverage_seconds": 0.0,
            "coverage_minutes": 0.0,
            "typical_interval_seconds": None,
            "sampling_frequency_hz": None,
            "interval_variation_percent": None,
            "duplicate_timestamp_count": 0,
            "out_of_order_count": 0,
            "gaps_detected": 0,
            "largest_gap_seconds": 0.0,
            "gap_threshold_seconds": minimum_gap_seconds,
            "gaps": [],
            "score": 0.0,
        }

    ordered_by_record = [
        timestamp
        for _, timestamp in timestamp_entries
    ]

    sorted_timestamps = sorted(ordered_by_record)

    duplicate_timestamp_count = count_duplicate_timestamps(
        sorted_timestamps
    )

    out_of_order_count = count_out_of_order_timestamps(
        ordered_by_record
    )

    intervals = calculate_positive_intervals(
        sorted_timestamps
    )

    typical_interval = (
        median(intervals)
        if intervals
        else None
    )

    gap_threshold = calculate_gap_threshold(
        typical_interval=typical_interval,
        gap_multiplier=gap_multiplier,
        minimum_gap_seconds=minimum_gap_seconds,
    )

    gaps = detect_timestamp_gaps(
        sorted_timestamps,
        gap_threshold_seconds=gap_threshold,
    )

    coverage_seconds = calculate_coverage_seconds(
        sorted_timestamps
    )

    interval_variation_percent = calculate_interval_variation(
        intervals,
        typical_interval,
    )

    sampling_frequency_hz = (
        round(1.0 / typical_interval, 4)
        if typical_interval
        and typical_interval > 0
        else None
    )

    score = calculate_timestamp_score(
        completeness_percent=completeness_percent,
        invalid_timestamp_count=invalid_timestamp_count,
        duplicate_timestamp_count=duplicate_timestamp_count,
        out_of_order_count=out_of_order_count,
        gaps_detected=len(gaps),
        interval_variation_percent=interval_variation_percent,
        total_records=total_records,
    )

    return {
        "available": True,
        "records_with_timestamp": timestamp_count,
        "missing_timestamp_count": missing_timestamp_count,
        "invalid_timestamp_count": invalid_timestamp_count,
        "completeness_percent": completeness_percent,
        "first_timestamp": sorted_timestamps[0].isoformat(),
        "last_timestamp": sorted_timestamps[-1].isoformat(),
        "coverage_seconds": round(coverage_seconds, 3),
        "coverage_minutes": round(
            coverage_seconds / 60,
            3,
        ),
        "typical_interval_seconds": (
            round(typical_interval, 4)
            if typical_interval is not None
            else None
        ),
        "sampling_frequency_hz": sampling_frequency_hz,
        "interval_variation_percent": interval_variation_percent,
        "duplicate_timestamp_count": duplicate_timestamp_count,
        "out_of_order_count": out_of_order_count,
        "gaps_detected": len(gaps),
        "largest_gap_seconds": (
            max(
                gap["duration_seconds"]
                for gap in gaps
            )
            if gaps
            else 0.0
        ),
        "gap_threshold_seconds": round(
            gap_threshold,
            3,
        ),
        "gaps": gaps[:100],
        "score": score,
    }


def assess_signal_quality(
    rows: Sequence[Mapping[str, Any]],
    *,
    expected_signals: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Calculate signal counts and completeness."""

    total_records = len(rows)

    signal_fields = {
        "heart_rate": (
            "heart_rate",
            "heart_rate_bpm",
            "hr",
        ),
        "pulse": (
            "pulse",
            "pulse_rate_bpm",
        ),
        "spo2": (
            "spo2",
            "oxygen_saturation",
        ),
        "hrv": (
            "hrv",
            "rmssd",
        ),
        "motion": (
            "motion",
            "cadence",
            "accelerometer",
        ),
        "temperature": (
            "temperature",
            "body_temperature",
            "skin_temperature",
            "chamber_temperature",
        ),
        "respiration": (
            "respiration_rate",
            "respiratory_rate",
            "breathing_rate",
        ),
        "pressure": (
            "pressure",
            "pressure_ata",
            "actual_ata",
        ),
    }

    signal_counts: dict[str, int] = {}
    signal_completeness: dict[str, float] = {}
    available_signals: list[str] = []

    for signal_name, fields in signal_fields.items():
        count = sum(
            1
            for row in rows
            if first_numeric(row, fields) is not None
        )

        signal_counts[signal_name] = count
        signal_completeness[signal_name] = percentage(
            count,
            total_records,
        )

        if count > 0:
            available_signals.append(signal_name)

    rr_record_count = sum(
        1
        for row in rows
        if extract_row_rr_values(row)
    )

    signal_counts["rr_intervals"] = rr_record_count
    signal_completeness["rr_intervals"] = percentage(
        rr_record_count,
        total_records,
    )

    if rr_record_count > 0:
        available_signals.append("rr_intervals")

    expected = [
        str(signal)
        for signal in (
            expected_signals or []
        )
    ]

    missing_expected_signals = [
        signal
        for signal in expected
        if signal_counts.get(signal, 0) <= 0
    ]

    relevant_completeness = [
        signal_completeness[signal]
        for signal in expected
        if signal in signal_completeness
    ]

    if relevant_completeness:
        score = round(
            sum(relevant_completeness)
            / len(relevant_completeness),
            2,
        )
    elif available_signals:
        score = round(
            max(
                signal_completeness[signal]
                for signal in available_signals
            ),
            2,
        )
    else:
        score = 0.0

    return {
        "available_signals": sorted(
            set(available_signals)
        ),
        "signal_counts": signal_counts,
        "completeness_percent": signal_completeness,
        "expected_signals": expected,
        "missing_expected_signals": missing_expected_signals,
        "score": score,
    }


def assess_rr_quality(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Assess RR validity and beat-to-beat artifacts."""

    raw_rr_values: list[float] = []

    for row in rows:
        raw_rr_values.extend(
            extract_row_rr_values(row)
        )

    if not raw_rr_values:
        return {
            "available": False,
            "samples_total": 0,
            "samples_valid": 0,
            "samples_invalid": 0,
            "artifacts_detected": 0,
            "valid_percent": 0.0,
            "artifact_percent": 0.0,
            "minimum_rr_ms": None,
            "maximum_rr_ms": None,
            "average_rr_ms": None,
            "score": 0.0,
        }

    normalized_values = [
        normalize_rr_seconds(value)
        for value in raw_rr_values
    ]

    valid_values: list[float] = []
    invalid_count = 0
    artifact_count = 0
    previous_valid: float | None = None

    for value in normalized_values:
        if (
            value is None
            or not is_valid_rr_interval(value)
        ):
            invalid_count += 1
            continue

        if is_rr_artifact(
            value,
            previous_valid,
        ):
            artifact_count += 1
            continue

        valid_values.append(value)
        previous_valid = value

    total_samples = len(normalized_values)

    valid_percent = percentage(
        len(valid_values),
        total_samples,
    )

    artifact_percent = percentage(
        artifact_count,
        total_samples,
    )

    score = calculate_rr_score(
        valid_percent=valid_percent,
        artifact_percent=artifact_percent,
        total_samples=total_samples,
    )

    return {
        "available": True,
        "samples_total": total_samples,
        "samples_valid": len(valid_values),
        "samples_invalid": invalid_count,
        "artifacts_detected": artifact_count,
        "valid_percent": valid_percent,
        "artifact_percent": artifact_percent,
        "minimum_rr_ms": (
            round(min(valid_values) * 1000, 2)
            if valid_values
            else None
        ),
        "maximum_rr_ms": (
            round(max(valid_values) * 1000, 2)
            if valid_values
            else None
        ),
        "average_rr_ms": (
            round(
                sum(valid_values)
                / len(valid_values)
                * 1000,
                2,
            )
            if valid_values
            else None
        ),
        "score": score,
    }


def assess_physiological_ranges(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Detect values outside broad technical plausibility ranges.

    These checks are data-quality rules, not medical interpretation.
    """

    definitions = {
        "heart_rate": {
            "fields": (
                "heart_rate",
                "heart_rate_bpm",
                "hr",
            ),
            "minimum": HEART_RATE_MIN_BPM,
            "maximum": HEART_RATE_MAX_BPM,
        },
        "pulse": {
            "fields": (
                "pulse",
                "pulse_rate_bpm",
            ),
            "minimum": PULSE_MIN_BPM,
            "maximum": PULSE_MAX_BPM,
        },
        "spo2": {
            "fields": (
                "spo2",
                "oxygen_saturation",
            ),
            "minimum": SPO2_MIN_PERCENT,
            "maximum": SPO2_MAX_PERCENT,
        },
    }

    result: dict[str, Any] = {}
    total_checked = 0
    total_out_of_range = 0

    for signal_name, definition in definitions.items():
        values = [
            value
            for row in rows
            if (
                value := first_numeric(
                    row,
                    definition["fields"],
                )
            ) is not None
        ]

        out_of_range_values = [
            value
            for value in values
            if (
                value < definition["minimum"]
                or value > definition["maximum"]
            )
        ]

        total_checked += len(values)
        total_out_of_range += len(
            out_of_range_values
        )

        result[signal_name] = {
            "samples_checked": len(values),
            "samples_out_of_range": len(
                out_of_range_values
            ),
            "out_of_range_percent": percentage(
                len(out_of_range_values),
                len(values),
            ),
            "minimum_observed": (
                min(values)
                if values
                else None
            ),
            "maximum_observed": (
                max(values)
                if values
                else None
            ),
            "accepted_minimum": definition["minimum"],
            "accepted_maximum": definition["maximum"],
        }

    valid_percent = percentage(
        total_checked - total_out_of_range,
        total_checked,
    )

    return {
        "signals": result,
        "samples_checked": total_checked,
        "samples_out_of_range": total_out_of_range,
        "valid_percent": valid_percent,
        "score": valid_percent if total_checked else 100.0,
    }


def assess_merge_quality(
    rows: Iterable[Mapping[str, Any]],
    *,
    tolerance_ms: float = DEFAULT_MERGE_TOLERANCE_MS,
) -> dict[str, Any]:
    """Assess quality of a synchronized or merged telemetry timeline."""

    normalized_rows = [
        dict(row)
        for row in rows
        if isinstance(row, Mapping)
    ]

    total_records = len(normalized_rows)

    if total_records == 0:
        return {
            "schema_version": "merge-quality-v1",
            "score": 0.0,
            "level": "not_available",
            "records_total": 0,
            "records_synchronized": 0,
            "match_rate_percent": 0.0,
            "average_delta_ms": None,
            "maximum_delta_ms": None,
            "within_tolerance_count": 0,
            "within_tolerance_percent": 0.0,
            "tolerance_ms": tolerance_ms,
            "warnings": ["no_merged_records"],
        }

    synchronized_count = sum(
        1
        for row in normalized_rows
        if bool(row.get("synchronized"))
    )

    delta_values = [
        abs(value)
        for row in normalized_rows
        if (
            value := safe_float(
                row.get("delta_ms")
            )
        ) is not None
    ]

    within_tolerance_count = sum(
        1
        for value in delta_values
        if value <= tolerance_ms
    )

    match_rate_percent = percentage(
        synchronized_count,
        total_records,
    )

    within_tolerance_percent = percentage(
        within_tolerance_count,
        len(delta_values),
    )

    average_delta_ms = (
        round(
            sum(delta_values)
            / len(delta_values),
            2,
        )
        if delta_values
        else None
    )

    maximum_delta_ms = (
        round(max(delta_values), 2)
        if delta_values
        else None
    )

    score = calculate_merge_score(
        match_rate_percent=match_rate_percent,
        within_tolerance_percent=within_tolerance_percent,
        average_delta_ms=average_delta_ms,
        tolerance_ms=tolerance_ms,
    )

    warnings: list[str] = []

    if match_rate_percent < 70:
        warnings.append("low_merge_match_rate")

    if (
        within_tolerance_percent < 80
        and delta_values
    ):
        warnings.append(
            "many_samples_outside_merge_tolerance"
        )

    if (
        maximum_delta_ms is not None
        and maximum_delta_ms > tolerance_ms * 2
    ):
        warnings.append(
            "large_timestamp_alignment_delta"
        )

    return {
        "schema_version": "merge-quality-v1",
        "score": score,
        "level": quality_level(score),
        "records_total": total_records,
        "records_synchronized": synchronized_count,
        "match_rate_percent": match_rate_percent,
        "average_delta_ms": average_delta_ms,
        "maximum_delta_ms": maximum_delta_ms,
        "within_tolerance_count": within_tolerance_count,
        "within_tolerance_percent": within_tolerance_percent,
        "tolerance_ms": tolerance_ms,
        "warnings": warnings,
    }


def calculate_quality_score_components(
    *,
    total_records: int,
    timestamp_quality: Mapping[str, Any],
    signal_quality: Mapping[str, Any],
    rr_quality: Mapping[str, Any],
    physiological_quality: Mapping[str, Any],
) -> dict[str, dict[str, float]]:
    """Build weighted score components."""

    if total_records <= 0:
        return {
            "timestamp": {
                "score": 0.0,
                "weight": 0.35,
            },
            "signals": {
                "score": 0.0,
                "weight": 0.25,
            },
            "rr": {
                "score": 0.0,
                "weight": 0.25,
            },
            "physiological_ranges": {
                "score": 0.0,
                "weight": 0.15,
            },
        }

    rr_available = bool(
        rr_quality.get("available")
    )

    if rr_available:
        weights = {
            "timestamp": 0.35,
            "signals": 0.20,
            "rr": 0.30,
            "physiological_ranges": 0.15,
        }
    else:
        # RR should not lower quality when this source is not expected
        # to provide RR intervals, for example pulse-oximetry CSV.
        weights = {
            "timestamp": 0.45,
            "signals": 0.30,
            "rr": 0.0,
            "physiological_ranges": 0.25,
        }

    return {
        "timestamp": {
            "score": normalize_score(
                timestamp_quality.get("score")
            ),
            "weight": weights["timestamp"],
        },
        "signals": {
            "score": normalize_score(
                signal_quality.get("score")
            ),
            "weight": weights["signals"],
        },
        "rr": {
            "score": normalize_score(
                rr_quality.get("score")
            ),
            "weight": weights["rr"],
        },
        "physiological_ranges": {
            "score": normalize_score(
                physiological_quality.get("score")
            ),
            "weight": weights[
                "physiological_ranges"
            ],
        },
    }


def calculate_weighted_score(
    components: Mapping[str, Mapping[str, Any]],
) -> float:
    """Calculate weighted quality score."""

    weighted_sum = 0.0
    total_weight = 0.0

    for component in components.values():
        score = normalize_score(
            component.get("score")
        )
        weight = safe_float(
            component.get("weight")
        )

        if weight is None or weight <= 0:
            continue

        weighted_sum += score * weight
        total_weight += weight

    if total_weight <= 0:
        return 0.0

    return round(
        clamp(
            weighted_sum / total_weight,
            0,
            100,
        ),
        2,
    )


def calculate_timestamp_score(
    *,
    completeness_percent: float,
    invalid_timestamp_count: int,
    duplicate_timestamp_count: int,
    out_of_order_count: int,
    gaps_detected: int,
    interval_variation_percent: float | None,
    total_records: int,
) -> float:
    score = completeness_percent

    if total_records > 0:
        score -= percentage(
            invalid_timestamp_count,
            total_records,
        ) * 0.5

        score -= percentage(
            duplicate_timestamp_count,
            total_records,
        ) * 0.3

        score -= percentage(
            out_of_order_count,
            total_records,
        ) * 0.5

    score -= min(gaps_detected * 2.0, 25.0)

    if interval_variation_percent is not None:
        score -= min(
            max(
                interval_variation_percent - 20,
                0,
            ) * 0.15,
            15,
        )

    return round(
        clamp(score, 0, 100),
        2,
    )


def calculate_rr_score(
    *,
    valid_percent: float,
    artifact_percent: float,
    total_samples: int,
) -> float:
    if total_samples <= 0:
        return 0.0

    score = valid_percent
    score -= min(artifact_percent * 0.5, 25)

    if total_samples < 10:
        score = min(score, 40)
    elif total_samples < 30:
        score = min(score, 65)

    return round(
        clamp(score, 0, 100),
        2,
    )


def calculate_merge_score(
    *,
    match_rate_percent: float,
    within_tolerance_percent: float,
    average_delta_ms: float | None,
    tolerance_ms: float,
) -> float:
    score = (
        match_rate_percent * 0.6
        + within_tolerance_percent * 0.4
    )

    if (
        average_delta_ms is not None
        and tolerance_ms > 0
    ):
        delta_ratio = (
            average_delta_ms / tolerance_ms
        )

        if delta_ratio > 1:
            score -= min(
                (delta_ratio - 1) * 20,
                30,
            )

    return round(
        clamp(score, 0, 100),
        2,
    )


def build_quality_warnings(
    *,
    total_records: int,
    timestamp_quality: Mapping[str, Any],
    signal_quality: Mapping[str, Any],
    rr_quality: Mapping[str, Any],
    physiological_quality: Mapping[str, Any],
    overall_score: float,
) -> list[str]:
    """Generate stable machine-readable warning codes."""

    warnings: list[str] = []

    if total_records == 0:
        return ["no_telemetry_records"]

    if not timestamp_quality.get("available"):
        warnings.append("missing_timestamps")

    if (
        normalize_score(
            timestamp_quality.get(
                "completeness_percent"
            )
        ) < 90
    ):
        warnings.append(
            "incomplete_timestamp_coverage"
        )

    if (
        int(
            timestamp_quality.get(
                "invalid_timestamp_count"
            ) or 0
        ) > 0
    ):
        warnings.append("invalid_timestamps")

    if (
        int(
            timestamp_quality.get(
                "duplicate_timestamp_count"
            ) or 0
        ) > 0
    ):
        warnings.append("duplicate_timestamps")

    if (
        int(
            timestamp_quality.get(
                "out_of_order_count"
            ) or 0
        ) > 0
    ):
        warnings.append("out_of_order_timestamps")

    if (
        int(
            timestamp_quality.get(
                "gaps_detected"
            ) or 0
        ) > 0
    ):
        warnings.append("timestamp_gaps_detected")

    if signal_quality.get(
        "missing_expected_signals"
    ):
        warnings.append(
            "missing_expected_signals"
        )

    if rr_quality.get("available"):
        if (
            normalize_score(
                rr_quality.get("valid_percent")
            ) < 80
        ):
            warnings.append("low_rr_validity")

        if (
            normalize_score(
                rr_quality.get("artifact_percent")
            ) > 10
        ):
            warnings.append(
                "high_rr_artifact_ratio"
            )

        if (
            int(
                rr_quality.get("samples_valid")
                or 0
            ) < 10
        ):
            warnings.append(
                "insufficient_rr_samples"
            )

    if (
        normalize_score(
            physiological_quality.get(
                "valid_percent"
            )
        ) < 95
    ):
        warnings.append(
            "physiological_range_violations"
        )

    if overall_score < 40:
        warnings.append(
            "telemetry_quality_unusable"
        )
    elif overall_score < 70:
        warnings.append(
            "telemetry_quality_requires_review"
        )

    return list(dict.fromkeys(warnings))


def calculate_gap_threshold(
    *,
    typical_interval: float | None,
    gap_multiplier: float,
    minimum_gap_seconds: float,
) -> float:
    if (
        typical_interval is None
        or typical_interval <= 0
    ):
        return minimum_gap_seconds

    return max(
        typical_interval * max(gap_multiplier, 1),
        minimum_gap_seconds,
    )


def detect_timestamp_gaps(
    timestamps: Sequence[datetime],
    *,
    gap_threshold_seconds: float,
) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []

    for previous, current in zip(
        timestamps,
        timestamps[1:],
    ):
        try:
            difference = (
                current - previous
            ).total_seconds()
        except TypeError:
            continue

        if difference >= gap_threshold_seconds:
            gaps.append({
                "start": previous.isoformat(),
                "end": current.isoformat(),
                "duration_seconds": round(
                    difference,
                    3,
                ),
            })

    return gaps


def calculate_positive_intervals(
    timestamps: Sequence[datetime],
) -> list[float]:
    intervals: list[float] = []

    for previous, current in zip(
        timestamps,
        timestamps[1:],
    ):
        try:
            difference = (
                current - previous
            ).total_seconds()
        except TypeError:
            continue

        if difference > 0:
            intervals.append(difference)

    return intervals


def calculate_interval_variation(
    intervals: Sequence[float],
    typical_interval: float | None,
) -> float | None:
    if (
        not intervals
        or typical_interval is None
        or typical_interval <= 0
    ):
        return None

    absolute_deviations = [
        abs(value - typical_interval)
        for value in intervals
    ]

    median_deviation = median(
        absolute_deviations
    )

    return round(
        median_deviation
        / typical_interval
        * 100,
        2,
    )


def count_duplicate_timestamps(
    timestamps: Sequence[datetime],
) -> int:
    if not timestamps:
        return 0

    duplicates = 0
    previous: datetime | None = None

    for timestamp in timestamps:
        if (
            previous is not None
            and timestamp == previous
        ):
            duplicates += 1

        previous = timestamp

    return duplicates


def count_out_of_order_timestamps(
    timestamps: Sequence[datetime],
) -> int:
    count = 0

    for previous, current in zip(
        timestamps,
        timestamps[1:],
    ):
        try:
            if current < previous:
                count += 1
        except TypeError:
            continue

    return count


def calculate_coverage_seconds(
    timestamps: Sequence[datetime],
) -> float:
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


def extract_row_rr_values(
    row: Mapping[str, Any],
) -> list[float]:
    values: list[float] = []

    raw_list = row.get("rr_intervals")

    if isinstance(raw_list, (list, tuple)):
        for value in raw_list:
            numeric = safe_float(value)

            if numeric is not None:
                values.append(numeric)

    raw_single = row.get("rr_interval")

    if raw_single is not None:
        numeric = safe_float(raw_single)

        if numeric is not None:
            values.append(numeric)

    return values


def normalize_rr_seconds(
    value: Any,
) -> float | None:
    numeric = safe_float(value)

    if numeric is None:
        return None

    # Values greater than 10 are assumed to be milliseconds.
    if numeric > 10:
        numeric /= 1000

    return numeric


def is_valid_rr_interval(
    value: float | None,
) -> bool:
    return (
        value is not None
        and RR_MIN_SECONDS
        <= value
        <= RR_MAX_SECONDS
    )


def is_rr_artifact(
    value: float,
    previous_value: float | None,
) -> bool:
    if not is_valid_rr_interval(value):
        return True

    if previous_value is None:
        return False

    delta = abs(value - previous_value)

    ratio = (
        delta / previous_value
        if previous_value
        else 0.0
    )

    return (
        delta > RR_MAX_DELTA_SECONDS
        or ratio > RR_MAX_DELTA_RATIO
    )


def quality_level(score: float) -> str:
    if score >= 90:
        return "excellent"

    if score >= 75:
        return "good"

    if score >= 50:
        return "fair"

    if score > 0:
        return "poor"

    return "not_available"


def parse_timestamp(
    value: Any,
) -> datetime | None:
    if isinstance(value, datetime):
        return value

    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    try:
        return datetime.fromisoformat(
            text.replace("Z", "+00:00")
        )
    except ValueError:
        return None


def first_present(
    row: Mapping[str, Any],
    fields: Sequence[str],
) -> Any:
    for field in fields:
        value = row.get(field)

        if value not in (
            None,
            "",
            [],
            {},
        ):
            return value

    return None


def first_numeric(
    row: Mapping[str, Any],
    fields: Sequence[str],
) -> float | None:
    for field in fields:
        value = safe_float(
            row.get(field)
        )

        if value is not None:
            return value

    return None


def safe_float(
    value: Any,
) -> float | None:
    if (
        value is None
        or isinstance(value, bool)
    ):
        return None

    try:
        result = float(value)
    except (TypeError, ValueError):
        return None

    if result != result:
        return None

    return result


def percentage(
    numerator: int | float,
    denominator: int | float,
) -> float:
    if denominator <= 0:
        return 0.0

    return round(
        clamp(
            numerator / denominator * 100,
            0,
            100,
        ),
        2,
    )


def normalize_score(
    value: Any,
) -> float:
    numeric = safe_float(value)

    if numeric is None:
        return 0.0

    return round(
        clamp(numeric, 0, 100),
        2,
    )


def clamp(
    value: float,
    minimum: float,
    maximum: float,
) -> float:
    return min(
        max(value, minimum),
        maximum,
    )