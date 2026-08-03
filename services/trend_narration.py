"""Versioned, non-identifying facts and optional narration for session trends."""

from __future__ import annotations

import json
import os
from time import perf_counter
from statistics import mean
from typing import Any

from services.llm_observability import record_llm_event


TREND_FACT_SHEET_VERSION = "wellness-trend-fact-sheet-v1"
TREND_NARRATION_VERSION = "trend-narration-v1"
MIN_DATA_QUALITY = 70
MIN_TREND_SESSIONS = 3


def build_trend_fact_sheet(series: dict[str, Any]) -> dict[str, Any]:
    """Expose computed trends, never identity, raw samples, or prior narratives."""

    analyses = series.get("analyses") or []
    eligible = [row for row in analyses if eligible_row(row)]
    return {
        "schema_version": TREND_FACT_SHEET_VERSION,
        "series": {
            "requested_sessions": len(analyses),
            "eligible_sessions": len(eligible),
            "excluded_low_quality_sessions": len(analyses) - len(eligible),
            "sufficient_for_trend": len(eligible) >= MIN_TREND_SESSIONS,
            "confidence": confidence(len(eligible)),
            "window_size": series.get("series_limit"),
        },
        "protocol": select_fields(series.get("protocol") or {}, "code", "name", "target_ata"),
        "trend": {
            "wellness_score_direction": series.get("trend_direction"),
            "data_quality_direction": series.get("data_quality_trend"),
            "metrics": {
                "heart_rate_bpm": metric(eligible, "avg_reference_heart_rate"),
                "hrv_rmssd_ms": metric(eligible, "avg_hrv"),
                "spo2_percent": metric(eligible, "avg_spo2"),
                "duration_min": metric(eligible, "total_duration_min"),
            },
            "flagged_session_count": sum(
                1 for row in analyses
                if row.get("session_flagged") or row.get("anomaly_detected")
            ),
        },
        "data_quality": {
            "average_score": series.get("avg_data_quality"),
            "average_coverage_percent": series.get("avg_coverage"),
            "average_match_rate_percent": series.get("avg_match_rate"),
            "warning_counts": (series.get("data_quality_engine") or {}).get("warning_counts") or {},
        },
        "disclaimer": "Wglad wellness oparty na trendach wlasnych sesji i jakosci danych. Nie stanowi diagnozy medycznej.",
    }


def build_trend_ai_view(
    series: dict[str, Any],
    *,
    allow_llm: bool = False,
) -> dict[str, Any]:
    facts = build_trend_fact_sheet(series)
    narration = narrate(facts, allow_llm=allow_llm)
    return {
        "version": "trend-ai-v1",
        **narration,
        "fact_sheet": facts,
    }


def narrate(facts: dict[str, Any], *, allow_llm: bool) -> dict[str, Any]:
    fallback = deterministic_summary(facts)
    result = {
        "status": "disabled",
        "source": "deterministic_fallback",
        "text": fallback,
        "provider": None,
        "model": None,
        "narration_version": TREND_NARRATION_VERSION,
        "fact_sheet_version": TREND_FACT_SHEET_VERSION,
    }
    if not allow_llm or not enabled():
        return result
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {**result, "status": "missing_api_key", "provider": "openai"}
    started_at = perf_counter()
    model = os.getenv("OPENAI_MODEL", "gpt-5-mini")
    try:
        from openai import OpenAI

        response = OpenAI(api_key=api_key).responses.create(
            model=model,
            instructions=prompt(),
            input=json.dumps(facts, ensure_ascii=True),
            max_output_tokens=400,
            store=False,
        )
        text = "\n".join(
            line.strip() for line in str(response.output_text or "").splitlines() if line.strip()
        )[:1400]
        if not valid(text, facts):
            raise ValueError("invalid trend narration")
        record_llm_event(
            feature="trend_ai",
            status="generated",
            provider="openai",
            model=model,
            started_at=started_at,
            response=response,
        )
        return {**result, "status": "generated", "source": "llm", "text": text, "provider": "openai", "model": model}
    except Exception as exc:
        record_llm_event(
            feature="trend_ai",
            status="fallback_after_provider_error",
            provider="openai",
            model=model,
            started_at=started_at,
            error=exc,
        )
        return {**result, "status": "fallback_after_provider_error", "provider": "openai"}


def prompt() -> str:
    return """You are CoreLabTech Trend AI. Write a concise Polish wellness trend
summary using only the supplied versioned JSON fact sheet. Use exactly these headings:
Ograniczenia danych, Podsumowanie trendu, Zmiany w parametrach, Stabilne parametry,
Sesje odstawajace, Jakosc danych. Do not infer a trend when sufficient_for_trend is
false. Describe higher, lower, stable, missing or unavailable values without calling
them beneficial or harmful. Do not diagnose, infer causes, give medical advice,
recommend actions, or invent values. End with the supplied disclaimer verbatim."""


def valid(text: str, facts: dict[str, Any]) -> bool:
    normalized = text.lower()
    headings = ("ograniczenia danych", "podsumowanie trendu", "zmiany w parametrach", "stabilne parametry", "sesje odstawajace", "jakosc danych")
    forbidden = ("diagnoza", "rozpoznanie", "leczenie", "lek ", "choroba")
    return bool(
        text and len(text) <= 1400 and all(item in normalized for item in headings)
        and text.endswith(facts["disclaimer"])
        and not any(item in normalized for item in forbidden)
    )


def deterministic_summary(facts: dict[str, Any]) -> str:
    series = facts["series"]
    trend = facts["trend"]
    metrics = trend["metrics"]
    changed = "; ".join(
        f"{name}: {details['direction']}"
        for name, details in metrics.items() if details["available"]
    ) or "Brak wystarczajacych danych do oceny tego trendu"
    stable = ", ".join(
        name for name, details in metrics.items() if details["direction"] == "stable"
    ) or "Brak"
    summary = (
        f"Kierunek wyniku wellness: {trend.get('wellness_score_direction') or 'unknown'}."
        if series["sufficient_for_trend"]
        else "Brak wystarczajacej liczby sesji o odpowiedniej jakosci do oceny trendu."
    )
    return "\n\n".join((
        f"Ograniczenia danych\nKwalifikujace sesje: {series['eligible_sessions']}/{series['requested_sessions']}. Pewnosc trendu: {series['confidence']}.",
        f"Podsumowanie trendu\n{summary}",
        f"Zmiany w parametrach\n{changed}.",
        f"Stabilne parametry\n{stable}.",
        f"Sesje odstawajace\nOznaczone sesje: {trend['flagged_session_count']}.",
        f"Jakosc danych\nSrednia jakosc: {facts['data_quality'].get('average_score') or 'unknown'}.",
        facts["disclaimer"],
    ))


def eligible_row(row: dict[str, Any]) -> bool:
    try:
        return float(row.get("data_quality_score")) >= MIN_DATA_QUALITY
    except (TypeError, ValueError):
        return False


def metric(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    values = []
    for row in rows:
        try:
            values.append(float(row[key]))
        except (KeyError, TypeError, ValueError):
            continue
    if len(values) < 2:
        return {"available": False, "direction": "unavailable"}
    delta = values[-1] - values[0]
    return {
        "available": True,
        "direction": "stable" if abs(delta) < 0.01 else "higher" if delta > 0 else "lower",
        "first": round(values[0], 2), "last": round(values[-1], 2),
        "average": round(mean(values), 2),
        "percent_change": round(delta / values[0] * 100, 2) if values[0] else None,
    }


def confidence(count: int) -> str:
    return "high" if count >= 10 else "medium" if count >= 5 else "low"


def enabled() -> bool:
    return os.getenv("LLM_TREND_NARRATION_ENABLED", "false").strip().lower() == "true"


def select_fields(source: dict[str, Any], *fields: str) -> dict[str, Any]:
    return {field: source[field] for field in fields if source.get(field) not in (None, "")}
