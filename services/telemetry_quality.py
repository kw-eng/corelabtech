"""Measurement-quality metrics kept separate from wellness interpretation."""

from __future__ import annotations

from datetime import datetime, timezone
from statistics import median
from typing import Any


AGREEMENT_THRESHOLD_BPM = 10.0
SENSOR_MISMATCH_THRESHOLD_BPM = 20.0
MAX_CONTIGUOUS_GAP_SECONDS = 60.0


def assess_telemetry_quality(
    *,
    measurements: list[dict[str, Any]],
    usable: list[dict[str, Any]],
    time_alignment_quality: str,
) -> dict[str, Any]:
    """Return coverage and HR/PPG agreement without making health claims."""

    pairs = heart_rate_pulse_pairs(usable)
    differences = [pair[2] for pair in pairs]
    agreement_percent = (
        round(
            sum(value <= AGREEMENT_THRESHOLD_BPM for value in differences)
            / len(differences) * 100,
            2,
        )
        if differences
        else None
    )
    synchronized_coverage_percent = (
        round(len(usable) / len(measurements) * 100, 2)
        if measurements
        else 0.0
    )
    synchronized_temporal_coverage_percent = temporal_coverage_percent(
        measurements=measurements,
        usable=usable,
    )
    divergence_duration_seconds = sustained_divergence_seconds(pairs)

    quality_reasons = []
    if synchronized_coverage_percent < 80:
        quality_reasons.append("low_synchronized_coverage")
    if synchronized_temporal_coverage_percent < 80:
        quality_reasons.append("low_synchronized_temporal_coverage")
    if time_alignment_quality in {"low", "unknown"}:
        quality_reasons.append("time_alignment_uncertain")
    if agreement_percent is not None and agreement_percent < 80:
        quality_reasons.append("low_hr_pulse_agreement")
    if divergence_duration_seconds > 0:
        quality_reasons.append("sustained_hr_pulse_divergence")
    if not pairs:
        quality_reasons.append("hr_pulse_comparison_unavailable")

    if (
        synchronized_coverage_percent >= 90
        and synchronized_temporal_coverage_percent >= 90
        and time_alignment_quality == "high"
        and (agreement_percent is None or agreement_percent >= 90)
    ):
        signal_quality = "high"
    elif (
        synchronized_coverage_percent >= 60
        and synchronized_temporal_coverage_percent >= 60
        and time_alignment_quality not in {"low", "unknown"}
        and (agreement_percent is None or agreement_percent >= 60)
    ):
        signal_quality = "medium"
    else:
        signal_quality = "low"

    return {
        "synchronized_coverage_percent": synchronized_coverage_percent,
        "synchronized_temporal_coverage_percent": (
            synchronized_temporal_coverage_percent
        ),
        "hr_pulse_pair_count": len(pairs),
        "median_hr_pulse_difference_bpm": (
            round(float(median(differences)), 2) if differences else None
        ),
        "max_hr_pulse_difference_bpm": (
            round(max(differences), 2) if differences else None
        ),
        "hr_pulse_agreement_percent": agreement_percent,
        "hr_pulse_divergence_duration_seconds": divergence_duration_seconds,
        "signal_quality": signal_quality,
        "quality_reason": (
            ";".join(quality_reasons)
            if quality_reasons
            else "synchronized_signals_within_expected_agreement"
        ),
        "quality_reasons": quality_reasons,
    }


def heart_rate_pulse_pairs(
    rows: list[dict[str, Any]],
) -> list[tuple[datetime | None, float, float]]:
    """Return timestamped absolute differences for rows carrying both signals."""

    pairs = []
    for row in rows:
        heart_rate = numeric_value(
            row.get("heart_rate_bpm", row.get("heart_rate"))
        )
        pulse = numeric_value(
            row.get("pulse_rate_bpm", row.get("pulse"))
        )
        if heart_rate is None or pulse is None:
            continue
        pairs.append((parse_timestamp(row.get("timestamp")), heart_rate, abs(heart_rate - pulse)))

    return sorted(
        pairs,
        key=lambda pair: pair[0] or datetime.min,
    )


def sustained_divergence_seconds(
    pairs: list[tuple[datetime | None, float, float]],
) -> float:
    """Sum contiguous timestamp gaps where HR and PPG differ materially."""

    duration = 0.0
    previous_time: datetime | None = None
    previous_divergent = False

    for timestamp, _, difference in pairs:
        divergent = difference > SENSOR_MISMATCH_THRESHOLD_BPM
        if divergent and previous_divergent and timestamp and previous_time:
            try:
                gap = (timestamp - previous_time).total_seconds()
            except TypeError:
                gap = 0.0
            if 0 < gap <= MAX_CONTIGUOUS_GAP_SECONDS:
                duration += gap
        previous_time = timestamp
        previous_divergent = divergent

    return round(duration, 2)


def temporal_coverage_percent(
    *,
    measurements: list[dict[str, Any]],
    usable: list[dict[str, Any]],
) -> float:
    """Measure how much of the observed session span is synchronized."""

    all_times = sorted(
        timestamp
        for timestamp in (parse_timestamp(row.get("timestamp")) for row in measurements)
        if timestamp is not None
    )
    usable_times = sorted(
        timestamp
        for timestamp in (parse_timestamp(row.get("timestamp")) for row in usable)
        if timestamp is not None
    )
    if not all_times or not usable_times:
        return 0.0

    total_span = (all_times[-1] - all_times[0]).total_seconds()
    covered_span = (usable_times[-1] - usable_times[0]).total_seconds()
    if total_span <= 0:
        return 100.0
    return round(max(0.0, min(covered_span / total_span * 100, 100.0)), 2)


def numeric_value(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif value is None:
        return None
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None

    if parsed.tzinfo is not None:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed
