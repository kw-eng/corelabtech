"""Versioned HRV calculation from approved raw RR telemetry only."""

from __future__ import annotations

from datetime import datetime, timedelta
from math import sqrt
from statistics import mean
from typing import Any


HRV_ALGORITHM_VERSION = "rr-clean-v2"
RR_SOURCE_POLICY = "chest_hrm_ecg_only-v1"
MIN_RR_MS = 300.0
MAX_RR_MS = 2000.0
MAX_RR_DELTA_MS = 250.0
MAX_RR_DELTA_RATIO = 0.25
MIN_RR_FOR_SCORING = 20
DEFAULT_HRV_WINDOW_SECONDS = 60


def calculate_hrv_from_rr(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate HRV without trusting device summaries or unapproved RR."""

    source_rejected_count = 0
    source_approved_values = []
    for row in rows:
        values = rr_values_from_row(row)
        if not rr_source_is_approved(row):
            source_rejected_count += len(values)
            continue
        source_approved_values.extend(values)

    raw_values = [normalize_rr_ms(value) for value in source_approved_values]
    raw_values = [value for value in raw_values if value is not None]

    accepted: list[float] = []
    artifacts = 0
    previous: float | None = None
    for value in raw_values:
        if is_artifact(value, previous):
            artifacts += 1
            continue
        accepted.append(value)
        previous = value

    artifact_ratio = (
        round(artifacts / len(raw_values) * 100, 2)
        if raw_values
        else None
    )
    confidence = hrv_confidence(
        accepted_count=len(accepted),
        artifact_ratio=artifact_ratio,
    )

    return {
        "hrv_algorithm_version": HRV_ALGORITHM_VERSION,
        "rr_source_policy": RR_SOURCE_POLICY,
        "rr_source_rejected_count": source_rejected_count,
        "rr_raw_count": len(raw_values),
        "rr_count": len(accepted),
        "rr_artifact_count": artifacts,
        "artifact_ratio": artifact_ratio,
        "rmssd": rmssd(accepted),
        "sdnn": standard_deviation(accepted),
        "pnn50": pnn50(accepted),
        "hrv_confidence": confidence,
        "hrv_usable_for_scoring": confidence in {"medium", "high"},
    }


def calculate_hrv_windows(
    rows: list[dict[str, Any]],
    *,
    session_segments: list[dict[str, Any]] | None = None,
    window_seconds: int = DEFAULT_HRV_WINDOW_SECONDS,
) -> list[dict[str, Any]]:
    """Calculate HRV summaries in fixed windows inside configured phases."""

    if window_seconds <= 0:
        raise ValueError("window_seconds must be positive")

    timestamped_rows = timestamped(rows)
    if not timestamped_rows:
        return []

    phase_ranges = build_phase_ranges(
        start=timestamped_rows[0][0],
        end=timestamped_rows[-1][0],
        session_segments=session_segments or [],
    )
    grouped: dict[tuple[str, datetime], list[dict[str, Any]]] = {}
    for timestamp, row in timestamped_rows:
        phase, phase_start = phase_for_timestamp(timestamp, phase_ranges)
        elapsed = max(0, (timestamp - phase_start).total_seconds())
        window_start = phase_start + timedelta(
            seconds=int(elapsed // window_seconds) * window_seconds
        )
        grouped.setdefault((phase, window_start), []).append(row)

    return [
        {
            "phase": phase,
            "window_start": window_start,
            "window_end": window_start + timedelta(seconds=window_seconds),
            "sample_count": len(window_rows),
            **calculate_hrv_from_rr(window_rows),
        }
        for (phase, window_start), window_rows in sorted(grouped.items())
    ]


def annotate_hrv_rmssd_timeline(
    rows: list[dict[str, Any]],
    *,
    window_seconds: int = DEFAULT_HRV_WINDOW_SECONDS,
) -> None:
    """Attach a display-only rolling RMSSD series from approved raw RR packets."""

    if window_seconds <= 0:
        raise ValueError("window_seconds must be positive")

    accepted: list[tuple[datetime, float]] = []
    previous: float | None = None
    for timestamp, row in timestamped(rows):
        if not rr_source_is_approved(row):
            row["hrv"] = None
            continue

        for raw_value in rr_values_from_row(row):
            value = normalize_rr_ms(raw_value)
            if value is None or is_artifact(value, previous):
                continue
            accepted.append((timestamp, value))
            previous = value

        cutoff = timestamp - timedelta(seconds=window_seconds)
        accepted = [item for item in accepted if item[0] >= cutoff]
        row["hrv"] = rmssd([value for _, value in accepted])


def calculate_hrv_phase_metrics(
    rows: list[dict[str, Any]],
    *,
    session_segments: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Calculate one HRV summary per configured session phase."""

    timestamped_rows = timestamped(rows)
    if not timestamped_rows:
        return []

    phase_ranges = build_phase_ranges(
        start=timestamped_rows[0][0],
        end=timestamped_rows[-1][0],
        session_segments=session_segments or [],
    )
    grouped: dict[str, list[dict[str, Any]]] = {}
    bounds: dict[str, tuple[datetime, datetime]] = {}
    for phase, start, end in phase_ranges:
        bounds[phase] = (start, end)
    for timestamp, row in timestamped_rows:
        phase, _ = phase_for_timestamp(timestamp, phase_ranges)
        grouped.setdefault(phase, []).append(row)

    return [
        {
            "phase": phase,
            "window_start": bounds[phase][0],
            "window_end": bounds[phase][1],
            "sample_count": len(phase_rows),
            **calculate_hrv_from_rr(phase_rows),
        }
        for phase, phase_rows in grouped.items()
    ]


def requires_hrv_recalculation(stored_algorithm_version: str | None) -> bool:
    """Identify persisted HRV output that predates the active algorithm."""

    return stored_algorithm_version != HRV_ALGORITHM_VERSION


def rr_values_from_row(row: dict[str, Any]) -> list[Any]:
    packet = row.get("rr_intervals")
    if isinstance(packet, (list, tuple)) and packet:
        return list(packet)
    value = row.get("rr_interval")
    return [value] if value is not None else []


def rr_source_is_approved(row: dict[str, Any]) -> bool:
    """Allow HRV only from explicitly classified chest HRM ECG telemetry."""

    source_type = row.get("hr_source_type") or row.get("device_type")
    measurement_method = (
        row.get("hr_measurement_method")
        or row.get("measurement_method")
    )
    return source_type == "chest_hrm" and measurement_method == "ecg"


def normalize_rr_ms(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric * 1000 if 0.3 <= numeric <= 2.0 else numeric


def is_artifact(value: float, previous: float | None) -> bool:
    if not MIN_RR_MS <= value <= MAX_RR_MS:
        return True
    if previous is None:
        return False
    delta = abs(value - previous)
    return delta > MAX_RR_DELTA_MS and delta / previous > MAX_RR_DELTA_RATIO


def hrv_confidence(*, accepted_count: int, artifact_ratio: float | None) -> str:
    if accepted_count < 2:
        return "unavailable"
    if accepted_count < MIN_RR_FOR_SCORING or (artifact_ratio or 0) > 10:
        return "low"
    if accepted_count < 60 or (artifact_ratio or 0) > 5:
        return "medium"
    return "high"


def rmssd(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    differences = [(current - previous) ** 2 for previous, current in zip(values, values[1:])]
    return round(sqrt(sum(differences) / len(differences)), 2)


def standard_deviation(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    average = mean(values)
    return round(sqrt(sum((value - average) ** 2 for value in values) / (len(values) - 1)), 2)


def pnn50(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    differences = [abs(current - previous) for previous, current in zip(values, values[1:])]
    return round(sum(value > 50 for value in differences) / len(differences) * 100, 2)


def timestamped(rows: list[dict[str, Any]]) -> list[tuple[datetime, dict[str, Any]]]:
    result = [
        (timestamp, row)
        for row in rows
        if (timestamp := parse_timestamp(row.get("timestamp"))) is not None
    ]
    return sorted(result, key=lambda item: item[0])


def parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def build_phase_ranges(
    *,
    start: datetime,
    end: datetime,
    session_segments: list[dict[str, Any]],
) -> list[tuple[str, datetime, datetime]]:
    current = start
    ranges = []
    for segment in session_segments:
        try:
            duration_minutes = float(segment.get("actual_duration_min") or 0)
        except (TypeError, ValueError):
            duration_minutes = 0
        if duration_minutes <= 0:
            continue
        phase_end = current + timedelta(minutes=duration_minutes)
        ranges.append((str(segment.get("phase") or "during"), current, phase_end))
        current = phase_end
    return ranges or [("during", start, end + timedelta(microseconds=1))]


def phase_for_timestamp(
    timestamp: datetime,
    phase_ranges: list[tuple[str, datetime, datetime]],
) -> tuple[str, datetime]:
    for phase, start, end in phase_ranges:
        if start <= timestamp < end:
            return phase, start
    phase, start, _ = phase_ranges[-1]
    return phase, start
