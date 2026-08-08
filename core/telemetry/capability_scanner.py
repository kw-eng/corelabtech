"""Vendor-independent telemetry capability and quality scanner."""

from __future__ import annotations

from datetime import datetime
from statistics import median
from typing import Any

from core.telemetry.analysis_capabilities import AnalysisCapabilities


def _timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def scan_telemetry_rows(
    rows: list[dict[str, Any]],
    *,
    file_type: str,
    source_type: str = "external_telemetry",
) -> dict[str, Any]:
    """Describe data capabilities from normalized rows without vendor inference."""

    timestamps = sorted(
        timestamp
        for row in rows
        if (timestamp := _timestamp(row.get("timestamp_utc") or row.get("timestamp")))
    )
    intervals = [
        (right - left).total_seconds()
        for left, right in zip(timestamps, timestamps[1:])
        if (right - left).total_seconds() >= 0
    ]
    median_interval = median(intervals) if intervals else None
    gap_threshold = max(10.0, (median_interval or 1.0) * 3)
    gaps = sum(interval > gap_threshold for interval in intervals)
    duplicates = sum(interval == 0 for interval in intervals)
    coverage_seconds = (
        max(0.0, (timestamps[-1] - timestamps[0]).total_seconds())
        if len(timestamps) > 1
        else 0.0
    )
    rr_values = [
        value
        for row in rows
        for value in (row.get("rr_intervals") or [row.get("rr_interval")])
        if isinstance(value, (int, float))
    ]
    rr_artifacts = sum(value < 300 or value > 2000 for value in rr_values)
    signals = {
        "timestamp": bool(timestamps),
        "heart_rate": any(row.get("heart_rate_bpm") is not None for row in rows),
        "rr_intervals": bool(rr_values),
        "spo2": any(row.get("spo2") is not None for row in rows),
        "pulse": any(row.get("pulse_rate_bpm") is not None for row in rows),
        "motion": any(row.get("motion") is not None for row in rows),
        "pressure": any(row.get("pressure") is not None for row in rows),
        "session_markers": any(row.get("phase") is not None for row in rows),
    }
    issue_count = gaps + duplicates + (1 if rr_artifacts else 0)
    score = max(0, 100 - min(60, issue_count * 10) - (20 if not timestamps else 0))
    level = "excellent" if score >= 95 else "good" if score >= 80 else "fair" if score >= 60 else "poor"
    available = {
        AnalysisCapabilities.HEART_RATE: signals["heart_rate"],
        AnalysisCapabilities.HRV: signals["rr_intervals"],
        AnalysisCapabilities.OXYGEN: signals["spo2"],
        AnalysisCapabilities.MERGE: signals["timestamp"],
        AnalysisCapabilities.RECOVERY: any(signals.values()),
        AnalysisCapabilities.AI: any(signals.values()),
        AnalysisCapabilities.PDF: any(signals.values()),
        AnalysisCapabilities.LONGITUDINAL: any(signals.values()),
    }
    recommendation = (
        "ready_for_analysis" if available[AnalysisCapabilities.AI]
        else "upload_telemetry_with_timestamps"
    )
    return {
        "version": "telemetry-capabilities-v1",
        "file": {
            "type": file_type.upper(),
            "source_type": source_type,
            "records": len(rows),
            "coverage_seconds": round(coverage_seconds, 1),
        },
        "signals": signals,
        "quality": {
            "score": score,
            "level": level,
            "gaps_detected": gaps,
            "duplicate_timestamps": duplicates,
            "sampling_interval_seconds": round(median_interval, 3) if median_interval else None,
            "rr_artifact_ratio": round(rr_artifacts / len(rr_values), 4) if rr_values else None,
        },
        "analysis": {"available": available},
        "recommendation": recommendation,
    }
