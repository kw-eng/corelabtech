"""Localized, observational presentation of ``wellness-response-v1`` facts."""

from __future__ import annotations

from typing import Any


METRICS = (
    ("spo2_percentage_points", "spo2", "report.response_metric_spo2", "%", "pp"),
    ("heart_rate_bpm", "heart_rate_bpm", "report.response_metric_hr", "bpm", "bpm"),
    ("hrv_rmssd_ms", "hrv_rmssd_ms", "report.response_metric_hrv", "ms", "ms"),
)


def build_localized_session_response(
    response: dict[str, Any] | None, catalog: dict[str, str]
) -> dict[str, Any]:
    """Render known response facts without creating causal conclusions."""

    response = response or {}
    availability = response.get("availability") or {}
    delta_availability = availability.get("deltas") or {}
    pre = response.get("pre") or {}
    post = response.get("post") or {}
    during = response.get("during") or {}
    deltas = response.get("deltas") or {}
    subjective = (response.get("subjective_context") or {}).get("post") or {}

    def text(key: str, **params: Any) -> str:
        value = catalog.get(key, key)
        return value.format(**params) if params else value

    def value(number: Any, unit: str) -> str | None:
        if number is None:
            return None
        return f"{format_number(number)} {unit}".strip()

    delta_rows = []
    unavailable = []
    observations = []
    for delta_key, measure_key, label_key, unit, delta_unit in METRICS:
        label = text(label_key)
        delta = deltas.get(delta_key)
        if delta is None or not delta_availability.get(delta_key, delta is not None):
            unavailable.append(text("report.response_comparison_unavailable_metric", metric=label))
            continue
        before = value(pre.get(measure_key), unit)
        after = value(post.get(measure_key), unit)
        delta_text = f"{format_delta(delta)} {delta_unit}"
        delta_rows.append({
            "label": label,
            "before": before or text("report.response_not_available"),
            "after": after or text("report.response_not_available"),
            "delta": delta_text,
        })
        direction = "higher" if delta > 0 else "lower" if delta < 0 else "unchanged"
        observations.append(text(
            f"report.response_observation_{direction}",
            metric=label,
            value=delta_text,
        ))

    available_count = availability.get("available_delta_count")
    possible_count = availability.get("possible_delta_count")
    if not isinstance(available_count, int):
        available_count = len(delta_rows)
    if not isinstance(possible_count, int):
        possible_count = len(METRICS)

    subjective_rows = [
        {
            "label": text("report.context_energy_level"),
            "value": enum_text(text, subjective.get("energy_level")),
        },
        {
            "label": text("report.context_fatigue_level"),
            "value": enum_text(text, subjective.get("fatigue_level")),
        },
        {
            "label": text("report.context_relaxation_level"),
            "value": enum_text(text, subjective.get("relaxation_level")),
        },
        {
            "label": text("report.context_discomfort"),
            "value": enum_text(text, subjective.get("discomfort")),
        },
    ]
    subjective_rows = [row for row in subjective_rows if row["value"] is not None]

    limitation_codes = response.get("limitations") or []
    limitations = [
        localized_limitation(text, code)
        for code in limitation_codes
    ] + unavailable

    return {
        "title": text("report.session_response"),
        "pre": response_rows(pre, (
            ("spo2", "report.response_metric_spo2", "%"),
            ("heart_rate_bpm", "report.response_metric_hr", "bpm"),
            ("hrv_rmssd_ms", "report.response_metric_hrv", "ms"),
        ), text),
        "during": response_rows(during, (
            ("avg_spo2", "report.response_avg_spo2", "%"),
            ("min_spo2", "report.response_min_spo2", "%"),
            ("avg_heart_rate_bpm", "report.response_metric_hr", "bpm"),
            ("avg_pulse_bpm", "report.response_pulse", "bpm"),
            ("hrv_rmssd_ms", "report.response_metric_hrv", "ms"),
            ("duration_min", "report.label_duration", "min"),
            ("synchronization_percent", "report.label_sync_quality", "%"),
        ), text),
        "post": response_rows(post, (
            ("spo2", "report.response_metric_spo2", "%"),
            ("heart_rate_bpm", "report.response_metric_hr", "bpm"),
            ("hrv_rmssd_ms", "report.response_metric_hrv", "ms"),
        ), text),
        "deltas": delta_rows,
        "subjective": subjective_rows,
        "completeness": text(
            "report.response_completeness_value",
            available=available_count,
            possible=possible_count,
        ),
        "confidence": text(
            f"report.response_confidence_{response.get('confidence') or 'insufficient'}"
        ),
        "observations": observations or [text("report.response_no_objective_comparison")],
        "limitations": list(dict.fromkeys(limitations)),
    }


def response_rows(source: dict[str, Any], fields, text) -> list[dict[str, str]]:
    rows = []
    for key, label_key, unit in fields:
        display = source.get(key)
        if display is not None:
            rows.append({"label": text(label_key), "value": f"{format_number(display)} {unit}"})
    return rows


def enum_text(text, value: Any) -> str | None:
    if value in (None, ""):
        return None
    raw = str(value).strip().lower()
    translated = text(f"report.context_value_{raw}")
    return translated if translated != f"report.context_value_{raw}" else str(value)


def localized_limitation(text, code: Any) -> str:
    key = f"report.response_limitation_{str(code)}"
    translated = text(key)
    return translated if translated != key else text("report.response_limitation_quality_warning")


def format_number(value: Any) -> str:
    numeric = float(value)
    return str(int(numeric)) if numeric.is_integer() else f"{numeric:.2f}".rstrip("0").rstrip(".")


def format_delta(value: Any) -> str:
    display = format_number(value)
    return display if display.startswith("-") else f"+{display}"
