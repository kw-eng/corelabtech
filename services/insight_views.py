"""Deterministic, audience-specific views derived from analyzed session facts."""

from __future__ import annotations

from statistics import mean
from typing import Any


MIN_COMPARISON_DATA_QUALITY = 70


def build_operator_report(analysis: dict[str, Any]) -> dict[str, Any]:
    """Summarize operational facts without making medical interpretations."""

    features = analysis.get("features") or {}
    context = features.get("session_context") or {}
    quality_warnings = analysis.get("quality_warnings") or []
    execution_status = context.get("execution_status") or "unknown"
    attention_items = []
    if execution_status not in {"completed", "complete"}:
        attention_items.append("protocol_completion_requires_review")
    if analysis.get("data_quality_score") is not None and analysis["data_quality_score"] < 60:
        attention_items.append("data_quality_requires_review")
    if features.get("signal_quality") in {"low", "unknown"}:
        attention_items.append("sensor_quality_requires_review")
    if context.get("pressure_deviation") not in (None, 0, 0.0):
        attention_items.append("pressure_deviation_recorded")

    return {
        "version": "operator-report-v1",
        "protocol_execution_status": execution_status,
        "data_completeness_percent": features.get("match_rate"),
        "signal_quality": features.get("signal_quality"),
        "time_alignment_quality": features.get("time_alignment_quality"),
        "sensor_warnings": quality_warnings,
        "technical_attention_required": bool(attention_items),
        "attention_items": attention_items,
        "operator_action": (
            "review_required" if attention_items else "no_operator_intervention_required"
        ),
    }


def session_quality_label(data_quality_score: Any) -> str:
    """Classify session data quality deterministically for all report views."""

    try:
        score = float(data_quality_score)
    except (TypeError, ValueError):
        return "Needs review"
    if score >= 85:
        return "Excellent"
    if score >= 70:
        return "Good"
    if score >= 60:
        return "Fair"
    return "Needs review"


def build_session_comparison(history: dict[str, Any]) -> dict[str, Any]:
    """Compare a session to eligible personal history, never population data."""

    sessions = history.get("recent_sessions") or []
    latest = sessions[0] if sessions else None
    result = {
        "version": "session-comparison-v1",
        "available_sessions": len(sessions),
        "latest_available": bool(latest),
        "comparisons": {},
        "confidence": comparison_confidence(len(sessions)),
    }
    if not latest:
        return result

    for window_size in (1, 5, 10, 30):
        candidates = sessions[1:window_size + 1]
        reference = [
            session
            for session in candidates
            if session_has_comparison_quality(session)
        ]
        result["comparisons"][str(window_size)] = compare_to_reference(
            latest=latest,
            reference=reference,
            excluded_reference_sessions=len(candidates) - len(reference),
        )
    return result


def compare_to_reference(
    *,
    latest: dict[str, Any],
    reference: list[dict[str, Any]],
    excluded_reference_sessions: int = 0,
) -> dict[str, Any]:
    """Calculate change against a personal historical average when available."""

    if not session_has_comparison_quality(latest):
        return {
            "reference_sessions": len(reference),
            "excluded_reference_sessions": excluded_reference_sessions,
            "available": False,
            "reason": "latest_session_data_quality_below_threshold",
            "metrics": {},
        }

    metrics = {
        "rmssd": (latest.get("rmssd"), [row.get("rmssd") for row in reference]),
        "avg_hr": (latest.get("avg_hr"), [row.get("avg_hr") for row in reference]),
        "avg_spo2": (latest.get("avg_spo2"), [row.get("avg_spo2") for row in reference]),
        "data_quality_score": (
            latest.get("data_quality_score"),
            [row.get("data_quality_score") for row in reference],
        ),
    }
    return {
        "reference_sessions": len(reference),
        "excluded_reference_sessions": excluded_reference_sessions,
        "available": bool(reference),
        "reason": None if reference else "no_eligible_reference_sessions",
        "metrics": {
            name: metric_change(current=current, reference=values)
            for name, (current, values) in metrics.items()
        },
    }


def metric_change(*, current: Any, reference: list[Any]) -> dict[str, float | None]:
    try:
        current_value = float(current)
    except (TypeError, ValueError):
        current_value = None
    values = []
    for value in reference:
        try:
            values.append(float(value))
        except (TypeError, ValueError):
            continue
    baseline = round(mean(values), 2) if values else None
    delta = round(current_value - baseline, 2) if current_value is not None and baseline is not None else None
    percent = round(delta / baseline * 100, 2) if delta is not None and baseline else None
    return {
        "current": current_value,
        "reference_average": baseline,
        "delta": delta,
        "percent_change": percent,
        "direction": comparison_direction(delta),
    }


def session_has_comparison_quality(session: dict[str, Any]) -> bool:
    try:
        return float(session.get("data_quality_score")) >= MIN_COMPARISON_DATA_QUALITY
    except (TypeError, ValueError):
        return False


def comparison_direction(delta: float | None) -> str:
    if delta is None:
        return "unavailable"
    if delta > 0:
        return "higher"
    if delta < 0:
        return "lower"
    return "unchanged"


def comparison_confidence(session_count: int) -> str:
    if session_count >= 15:
        return "high"
    if session_count >= 5:
        return "medium"
    return "low"


def build_session_summary(
    *,
    analysis: dict[str, Any],
    narration: dict[str, Any],
) -> dict[str, Any]:
    """Expose one stable, audience-facing session-summary contract."""

    narration_status = narration.get("status") or "unavailable"
    return {
        "version": "session-summary-v1",
        "status": narration_status,
        "content": narration.get("text") or analysis.get("deterministic_summary") or "",
        "source": "llm" if narration_status == "generated" else "deterministic_fallback",
        "provider": narration.get("provider"),
        "model": narration.get("model"),
        "narration_version": narration.get("narration_version"),
        "fact_sheet_version": narration.get("fact_sheet_version"),
        "analysis_confidence": analysis.get("analysis_confidence"),
        "data_quality_score": analysis.get("data_quality_score"),
        "limitations": analysis.get("quality_warnings") or [],
        "disclaimer": analysis.get("wellness_disclaimer"),
    }


def build_recovery_coach(
    *,
    analysis: dict[str, Any],
    follow_ups: dict[str, dict[str, Any]] | None = None,
    check_in: dict[str, Any] | None = None,
    personal_history: list[dict[str, Any]] | None = None,
    follow_up: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a bounded, non-medical view of both recovery follow-up windows."""

    windows = dict(follow_ups or {})
    if follow_up and follow_up.get("follow_up_window"):
        windows.setdefault(follow_up["follow_up_window"], follow_up)
    history = personal_history or []
    comparisons = {
        window: build_recovery_window_comparison(
            current=windows.get(window),
            check_in=check_in or {},
            personal_history=history,
            window=window,
        )
        for window in ("one_hour", "next_day")
    }
    recorded_count = len(windows)
    status = (
        "follow_up_pending"
        if not recorded_count
        else "follow_up_complete"
        if recorded_count == 2
        else "follow_up_recorded"
    )
    if recorded_count == 2:
        summary = "Zapisano follow-up po godzinie i nastepnego dnia; oba sa gotowe do porownania."
    elif recorded_count:
        summary = "Zapisano jeden follow-up; drugie okno pozostaje dostepne do uzupelnienia."
    else:
        summary = "Brak danych follow-up do oceny recovery po sesji."

    latest = max(
        windows.values(), key=lambda entry: entry.get("recorded_at") or "", default=None
    )
    return {
        "version": "recovery-coach-v2",
        "status": status,
        "summary": summary,
        "follow_up": latest,
        "follow_ups": {window: windows.get(window) for window in ("one_hour", "next_day")},
        "comparisons": comparisons,
        "history": recovery_history_summary(history),
        "follow_up_schedule": [
            {
                "follow_up_window": window,
                "status": "recorded" if windows.get(window) else "pending",
                "reminder_key": f"recovery_follow_up_{window}",
            }
            for window in ("one_hour", "next_day")
        ],
        "data_quality_score": analysis.get("data_quality_score"),
        "limitations": analysis.get("quality_warnings") or [],
        "monitor_before_next_session": ["energy_level", "fatigue_level", "sleep_quality"],
    }


def build_recovery_window_comparison(
    *,
    current: dict[str, Any] | None,
    check_in: dict[str, Any],
    personal_history: list[dict[str, Any]],
    window: str,
) -> dict[str, Any]:
    """Compare recorded facts with the same session and eligible personal history."""

    reference = [entry for entry in personal_history if entry.get("follow_up_window") == window]
    metrics = {}
    for metric in ("heart_rate_bpm", "spo2"):
        value = current.get(metric) if current else None
        check_in_value = recovery_check_in_value(check_in, metric)
        history_values = [entry.get(metric) for entry in reference]
        metrics[metric] = {
            "current": numeric_or_none(value),
            "check_in": numeric_or_none(check_in_value),
            "check_in_delta": metric_delta(value, check_in_value),
            "personal_history": metric_change(current=value, reference=history_values),
        }
    return {
        "available": bool(current),
        "reference_sessions": len({entry.get("session_id") for entry in reference if entry.get("session_id")}),
        "history_available": len(reference) >= 3,
        "metrics": metrics,
    }


def recovery_check_in_value(check_in: dict[str, Any], metric: str) -> Any:
    if metric == "heart_rate_bpm":
        return check_in.get("heart_rate_bpm", check_in.get("pulse"))
    return check_in.get(metric)


def numeric_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def metric_delta(current: Any, reference: Any) -> float | None:
    current_value = numeric_or_none(current)
    reference_value = numeric_or_none(reference)
    if current_value is None or reference_value is None:
        return None
    return round(current_value - reference_value, 2)


def recovery_history_summary(history: list[dict[str, Any]]) -> dict[str, Any]:
    """Expose only count and numeric personal baselines used by the coach."""

    result = {"available_entries": len(history), "windows": {}}
    for window in ("one_hour", "next_day"):
        entries = [entry for entry in history if entry.get("follow_up_window") == window]
        result["windows"][window] = {
            "entries": len(entries),
            "eligible_for_comparison": len(entries) >= 3,
            "heart_rate_bpm_average": average_numeric(entry.get("heart_rate_bpm") for entry in entries),
            "spo2_average": average_numeric(entry.get("spo2") for entry in entries),
        }
    return result


def average_numeric(values: Any) -> float | None:
    numbers = [number for value in values if (number := numeric_or_none(value)) is not None]
    return round(mean(numbers), 2) if numbers else None
