"""Small, explicit representation for the Research dashboard analysis view."""

from __future__ import annotations

import json
from typing import Any


DASHBOARD_VIEW = "research_dashboard"
MAX_TIMELINE_SAMPLES = 2_000


def sample_timeline(timeline: Any, requested_samples: int | None) -> tuple[list[Any], int, int]:
    """Return evenly sampled timeline rows while retaining endpoint semantics."""

    rows = timeline if isinstance(timeline, list) else []
    total = len(rows)
    if not requested_samples or requested_samples <= 1 or total <= requested_samples:
        return rows, total, total

    sample_count = min(requested_samples, MAX_TIMELINE_SAMPLES)
    last_index = total - 1
    sampled = [
        rows[round(index * last_index / (sample_count - 1))]
        for index in range(sample_count)
    ]
    return sampled, total, len(sampled)


def dashboard_timeline_point(row: Any) -> dict[str, Any]:
    """Keep only scalar measurements used by the dashboard chart."""

    row = row if isinstance(row, dict) else {}
    return {
        "timestamp": row.get("timestamp") or row.get("time"),
        "heart_rate": _scalar(row.get("heart_rate_bpm", row.get("heart_rate"))),
        "pulse": _scalar(row.get("pulse_rate_bpm", row.get("pulse"))),
        "spo2": _scalar(row.get("spo2")),
        "hrv": _scalar(row.get("hrv")),
    }


def build_research_dashboard_projection(
    result: dict[str, Any], *, timeline_sample: int | None
) -> dict[str, Any]:
    """Return only fields consumed by ``research_dashboard.html``.

    The complete persisted result remains available through the legacy response.
    This projection intentionally excludes raw/source telemetry, RR intervals,
    provenance and large analysis internals that the dashboard does not render.
    """

    analysis = result.get("result") or {}
    sampled, total, sample_count = sample_timeline(
        analysis.get("timeline"), timeline_sample
    )
    features = analysis.get("features") or result.get("features") or {}

    return {
        "ai_result_id": result.get("ai_result_id"),
        "merge_id": result.get("merge_id"),
        "session_id": result.get("session_id"),
        "overall_score": analysis.get("overall_score", result.get("overall_score")),
        "data_quality_score": analysis.get(
            "data_quality_score", result.get("data_quality_score")
        ),
        "analysis_confidence": analysis.get("analysis_confidence"),
        "anomaly_detected": analysis.get(
            "anomaly_detected", result.get("anomaly_detected")
        ),
        "wellness_status": analysis.get("wellness_status"),
        "quality_warnings": analysis.get("quality_warnings") or [],
        "summary": analysis.get("summary", result.get("summary")),
        "features": {
            key: features.get(key)
            for key in ("avg_spo2", "avg_csv_spo2", "avg_pulse", "avg_csv_pulse", "avg_hrv")
            if key in features
        },
        "timeline": [dashboard_timeline_point(row) for row in sampled],
        "timeline_total": total,
        "timeline_sampled": sample_count,
        "session_summary": analysis.get("session_summary"),
        "session_comparison": analysis.get("session_comparison"),
        "recovery_coach": analysis.get("recovery_coach"),
        "reasons": analysis.get("reasons") or [],
        "positive_findings": analysis.get("positive_findings") or [],
        "wellness_disclaimer": analysis.get("wellness_disclaimer"),
        "medical_disclaimer": analysis.get("medical_disclaimer"),
    }


def _scalar(value: Any) -> float | int | str | bool | None:
    """Prevent nested raw telemetry structures from entering dashboard JSON."""

    return value if isinstance(value, (float, int, str, bool)) or value is None else None


def serialized_field_sizes(payload: dict[str, Any]) -> dict[str, int]:
    """Return per-field JSON byte sizes for development diagnostics only."""

    return {
        key: len(json.dumps({key: value}, default=str, separators=(",", ":")).encode("utf-8"))
        for key, value in payload.items()
    }
