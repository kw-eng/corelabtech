"""Small, explicit representation for the Research dashboard analysis view."""

from __future__ import annotations

import json
from typing import Any

from services.llm_narration import (
    build_session_fact_sheet,
    localized_deterministic_summary,
)
from services.session_response_presentation import (
    build_localized_session_response,
)


DASHBOARD_VIEW = "research_dashboard"
MAX_TIMELINE_SAMPLES = 2_000

# These are measured or presentation-oriented values consumed by the current
# operator, AI Lab, chamber, admin and dashboard views. Raw RR packets,
# algorithm configuration, thresholds, provenance structures and persistence
# metadata deliberately remain server-side.
PRESENTATION_FEATURE_KEYS = frozenset({
    "samples_total", "samples_synchronized", "match_rate", "quality_warnings",
    "avg_spo2", "min_spo2", "max_spo2", "avg_csv_spo2", "min_csv_spo2", "max_csv_spo2",
    "avg_pulse", "min_pulse", "max_pulse", "avg_csv_pulse", "min_csv_pulse", "max_csv_pulse",
    "avg_heart_rate", "min_heart_rate", "max_heart_rate", "avg_fit_hr", "min_fit_hr", "max_fit_hr",
    "avg_hrv", "data_quality_score", "fit_samples", "csv_samples", "csv_pulse_artifacts",
    "signal_quality", "time_alignment_quality",
})

PRESENTATION_ANALYSIS_KEYS = frozenset({
    "overall_score", "score", "wellness_response_score", "data_quality_score",
    "wellness_status", "wellness_disclaimer", "score_type", "analysis_confidence",
    "anomaly_detected", "anomaly", "risk_level", "summary", "quality_warnings",
    "reasons", "positive_findings", "session_response", "session_summary",
    "session_comparison", "recovery_coach", "session_context",
})


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


def build_analysis_presentation(
    result: dict[str, Any], *, timeline_sample: int | None = None
) -> dict[str, Any]:
    """Return the stable, browser-safe analysis DTO for legacy consumers.

    The persisted analysis object remains an internal server representation.
    This DTO preserves the values rendered by existing non-dashboard views but
    excludes model/provider data, ownership, raw telemetry, RR intervals,
    scoring configuration, and arbitrary persistence fields.
    """

    analysis = result.get("result") or {}
    features = analysis.get("features") or result.get("features") or {}
    sampled, total, sample_count = sample_timeline(
        analysis.get("timeline"), timeline_sample
    )
    presentation_features = {
        key: _scalar(features.get(key))
        for key in PRESENTATION_FEATURE_KEYS
        if key in features and _scalar(features.get(key)) is not None
    }
    if isinstance(features.get("quality_warnings"), list):
        presentation_features["quality_warnings"] = [
            value for value in features["quality_warnings"] if isinstance(value, str)
        ]

    fields = {
        key: analysis.get(key, result.get(key))
        for key in PRESENTATION_ANALYSIS_KEYS
        if analysis.get(key, result.get(key)) is not None
    }
    fields["features"] = presentation_features
    fields["timeline"] = [dashboard_timeline_point(row) for row in sampled]
    fields["timeline_total"] = total
    fields["timeline_sampled"] = sample_count

    # ``result`` is retained as a compatibility envelope for legacy views, but
    # is explicitly reconstructed from the safe presentation fields.
    return {
        key: result.get(key)
        for key in ("ai_result_id", "merge_id", "session_id", "created_at")
        if result.get(key) is not None
    } | {
        "client_id": analysis.get("client_id") or result.get("client_id"),
        "status": "ok",
        **fields,
        "result": fields,
    }


def build_research_dashboard_projection(
    result: dict[str, Any], *, timeline_sample: int | None,
    catalog: dict[str, str] | None = None,
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
    fact_sheet = build_session_fact_sheet(analysis)
    session_response = analysis.get("session_response") or fact_sheet.get(
        "session_response"
    )

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
        "session_response": session_response,
        "session_response_presentation": (
            build_localized_session_response(session_response, catalog)
            if catalog is not None
            else None
        ),
        "timeline": [dashboard_timeline_point(row) for row in sampled],
        "timeline_total": total,
        "timeline_sampled": sample_count,
        # Stored narration can have been created in another locale.  Use the
        # current analysis facts for a locale-specific deterministic dashboard
        # summary instead of reusing that persisted text.
        "session_summary": (
            {
                "content": localized_deterministic_summary(
                    fact_sheet, catalog
                ),
                "source": "deterministic_fallback",
                "analysis_confidence": analysis.get("analysis_confidence"),
                "data_quality_score": analysis.get("data_quality_score"),
                "limitations": analysis.get("quality_warnings") or [],
                # Historical result JSON can contain narration in another
                # locale. Render this customer-facing notice from the active
                # catalog instead of forwarding persisted prose.
                "disclaimer": catalog.get("mission.wellness_disclaimer"),
            }
            if catalog is not None
            else analysis.get("session_summary")
        ),
        "session_comparison": analysis.get("session_comparison"),
        "recovery_coach": analysis.get("recovery_coach"),
        "reasons": analysis.get("reasons") or [],
        "positive_findings": analysis.get("positive_findings") or [],
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
