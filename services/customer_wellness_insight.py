"""Customer-first wellness insight projections built from existing facts only."""

from __future__ import annotations

from typing import Any


def build_session_customer_insight(*, analysis: dict[str, Any], response_presentation: dict[str, Any] | None, catalog: dict[str, str]) -> dict[str, Any]:
    """Create concise, localized copy without changing analytical semantics."""
    response_presentation = response_presentation or {}
    status = _known_status((analysis.get("result") or {}).get("wellness_status"))
    subjective = response_presentation.get("subjective") or []
    changes = response_presentation.get("deltas") or []
    limitations = response_presentation.get("limitations") or []
    observations = response_presentation.get("observations") or []
    summary = [_text(catalog, f"customer.session.summary_{status}")]
    if subjective:
        summary.append(_text(catalog, "customer.session.self_reported", details="; ".join(f"{row['label']}: {row['value']}" for row in subjective)))
    elif observations:
        summary.append(observations[0])
    return {
        "status": _text(catalog, f"customer.status_{status}"),
        "headline": _text(catalog, "customer.session.headline"),
        "summary": " ".join(summary[:2]),
        "changes": changes,
        "self_reported": subjective,
        "watch_items": limitations[:3],
        "next_step": _text(catalog, "customer.session.next_step_limited" if limitations else "customer.session.next_step_complete"),
        "confidence": response_presentation.get("confidence") or _text(catalog, "customer.confidence_unavailable"),
        "confidence_reason": _text(catalog, "customer.confidence_reason"),
    }


def build_series_customer_insight(*, series_data: dict[str, Any], catalog: dict[str, str]) -> dict[str, Any]:
    """Describe the existing series trend in customer language, not audit jargon."""
    trend = _known_trend(series_data.get("trend_direction"))
    records = _integer(series_data.get("records"))
    warnings = (series_data.get("data_quality_engine") or {}).get("warning_counts") or {}
    return {
        "status": _text(catalog, f"customer.trend_{trend}"),
        "headline": _text(catalog, "customer.series.headline"),
        "summary": _text(catalog, f"customer.series.summary_{trend}", sessions=records),
        "pattern": _text(catalog, "customer.series.pattern_developing" if records < 10 else "customer.series.pattern_established"),
        "watch_items": [_text(catalog, "customer.series.watch_quality")] if warnings else [],
        "next_step": _text(catalog, "customer.series.next_step"),
        "confidence": _text(catalog, _series_confidence_key(series_data.get("evidence_level"))),
        "sessions_analyzed": records,
    }


def _text(catalog: dict[str, str], key: str, **params: Any) -> str:
    value = catalog.get(key, key)
    return value.format(**params) if params else value


def _known_status(value: Any) -> str:
    status = str(value or "unknown").strip().lower()
    return status if status in {"stable", "elevated_load", "data_quality_warning"} else "unknown"


def _known_trend(value: Any) -> str:
    trend = str(value or "insufficient").strip().lower()
    return trend if trend in {"stable", "improving", "declining"} else "emerging"


def _series_confidence_key(value: Any) -> str:
    level = str(value or "insufficient").strip().lower()
    return {"established": "customer.confidence_high", "emerging": "customer.confidence_moderate", "preliminary": "customer.confidence_moderate"}.get(level, "customer.confidence_limited")


def _integer(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
