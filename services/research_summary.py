"""Versioned research facts and optional constrained narration for one session."""

from __future__ import annotations

import json
import os
from time import perf_counter
from typing import Any

from services.llm_observability import record_llm_event


RESEARCH_FACT_SHEET_VERSION = "research-fact-sheet-v1"
RESEARCH_SUMMARY_VERSION = "research-summary-v1"
RESEARCH_NARRATION_VERSION = "research-narration-v1"
RESEARCH_DEFAULT_MODEL = "gpt-5-mini"
RESEARCH_MAX_NARRATION_CHARACTERS = 1600


def build_research_fact_sheet(analysis: dict[str, Any]) -> dict[str, Any]:
    """Minimize an analysis to reproducible, non-identifying research facts."""

    features = analysis.get("features") or {}
    context = features.get("session_context") or {}
    timing = context.get("session_timing") or {}
    return {
        "schema_version": RESEARCH_FACT_SHEET_VERSION,
        "analysis": {
            "model_name": analysis.get("model_name"),
            "model_version": analysis.get("model_version"),
            "analysis_confidence": analysis.get("analysis_confidence"),
            "data_quality_score": analysis.get("data_quality_score"),
            "quality_warnings": analysis.get("quality_warnings") or [],
        },
        "protocol": {
            "code": (analysis.get("protocol") or {}).get("code"),
            "target_ata": context.get("target_ata"),
            "actual_ata": context.get("actual_ata"),
            "execution_status": context.get("execution_status"),
            "total_duration_min": timing.get("total_duration_min"),
        },
        "measurements": {
            "samples_total": features.get("samples_total"),
            "samples_synchronized": features.get("samples_synchronized"),
            "avg_spo2": features.get("avg_spo2"),
            "min_spo2": features.get("min_spo2"),
            "avg_reference_heart_rate": features.get("avg_reference_heart_rate"),
            "rr_count": features.get("rr_count"),
            "rmssd": features.get("avg_hrv"),
            "sdnn": features.get("sdnn"),
            "pnn50": features.get("pnn50"),
            "artifact_ratio": features.get("artifact_ratio"),
            "hrv_algorithm_version": features.get("hrv_algorithm_version"),
            "hrv_window_seconds": features.get("hrv_window_seconds"),
        },
        "limitations": {
            "signal_quality": features.get("signal_quality"),
            "time_alignment_quality": features.get("time_alignment_quality"),
            "hrv_confidence": features.get("hrv_confidence"),
            "quality_warnings": analysis.get("quality_warnings") or [],
        },
        "disclaimer": (
            "Podsumowanie badawcze opisuje dane obserwacyjne jednej sesji wellness "
            "i nie stanowi diagnozy medycznej."
        ),
    }


def build_research_summary(analysis: dict[str, Any]) -> dict[str, Any]:
    """Return deterministic sections plus optional LLM narration over the fact sheet."""

    facts = build_research_fact_sheet(analysis)
    protocol = facts["protocol"]
    measurements = facts["measurements"]
    limitations = facts["limitations"]
    unavailable = "Brak danych."
    sections = {
        "abstract": (
            "Opis obserwacyjny pojedynczej sesji wellness oparty na "
            "zsynchronizowanych danych i wersjonowanym modelu analizy."
        ),
        "methods": (
            f"Model: {facts['analysis'].get('model_version') or unavailable}; "
            f"probki: {measurements.get('samples_synchronized') or 0}/"
            f"{measurements.get('samples_total') or 0}; "
            f"protokol: {protocol.get('code') or unavailable}; "
            f"HRV: {measurements.get('hrv_algorithm_version') or unavailable}."
        ),
        "observations": (
            f"SpO2 srednie/minimum: {measurements.get('avg_spo2') or unavailable}/"
            f"{measurements.get('min_spo2') or unavailable}; "
            f"HR referencyjne: {measurements.get('avg_reference_heart_rate') or unavailable}; "
            f"RMSSD: {measurements.get('rmssd') or unavailable}."
        ),
        "interpretation": (
            "Wyniki opisuja wylacznie zaobserwowane parametry i ich jakosc "
            "w kontekscie sesji."
        ),
        "limitations": (
            f"Pewnosc analizy: {facts['analysis'].get('analysis_confidence') or unavailable}; "
            f"jakosc sygnalu: {limitations.get('signal_quality') or unavailable}; "
            f"ostrzezenia: {', '.join(limitations.get('quality_warnings') or []) or unavailable}."
        ),
        "future_data_required": (
            "Dodatkowe sesje o porownywalnym protokole i jakosci danych sa potrzebne "
            "do wnioskow podluznych."
        ),
    }
    narration = narrate_research_fact_sheet(facts, sections)
    return {
        "version": RESEARCH_SUMMARY_VERSION,
        "fact_sheet_version": RESEARCH_FACT_SHEET_VERSION,
        "status": narration["status"],
        "fact_sheet": facts,
        "sections": sections,
        "narration": narration,
        "disclaimer": facts["disclaimer"],
    }


def narrate_research_fact_sheet(
    facts: dict[str, Any], sections: dict[str, str]
) -> dict[str, Any]:
    """Optionally narrate only verified facts and retain a deterministic fallback."""

    fallback = "\n\n".join(
        (
            "Abstract\n" + sections["abstract"],
            "Methods\n" + sections["methods"],
            "Observations\n" + sections["observations"],
            "Interpretation\n" + sections["interpretation"],
            "Limitations\n" + sections["limitations"],
            "Future data required\n" + sections["future_data_required"],
            facts["disclaimer"],
        )
    )
    result = {
        "source": "deterministic_fallback",
        "text": fallback,
        "provider": None,
        "model": None,
        "narration_version": RESEARCH_NARRATION_VERSION,
        "fact_sheet_version": RESEARCH_FACT_SHEET_VERSION,
        "status": "disabled",
    }
    if not research_narration_enabled():
        return result
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {**result, "status": "missing_api_key", "provider": "openai"}
    started_at = perf_counter()
    model = os.getenv("OPENAI_MODEL", RESEARCH_DEFAULT_MODEL)
    try:
        from openai import OpenAI

        response = OpenAI(api_key=api_key).responses.create(
            model=model,
            instructions=research_narration_instructions(),
            input=json.dumps(facts, ensure_ascii=True),
            max_output_tokens=450,
            store=False,
        )
        text = normalize_research_narration(getattr(response, "output_text", ""))
        if not valid_research_narration(text, facts):
            raise ValueError("LLM research narration failed the output policy")
        record_llm_event(
            feature="research_ai",
            status="generated",
            provider="openai",
            model=model,
            started_at=started_at,
            response=response,
        )
        return {
            **result,
            "source": "llm",
            "text": text,
            "provider": "openai",
            "model": model,
            "status": "generated",
        }
    except Exception as exc:
        record_llm_event(
            feature="research_ai",
            status="fallback_after_provider_error",
            provider="openai",
            model=model,
            started_at=started_at,
            error=exc,
        )
        return {**result, "status": "fallback_after_provider_error", "provider": "openai"}


def research_narration_enabled() -> bool:
    return os.getenv("LLM_RESEARCH_NARRATION_ENABLED", "false").strip().lower() == "true"


def research_narration_instructions() -> str:
    return """You are CoreLabTech Research AI. Write a concise scientific-style summary
in Polish using only the supplied versioned JSON fact sheet. Use exactly these headings:
Abstract, Methods, Observations, Interpretation, Limitations, Future data required.
Make all data limitations explicit in the Limitations section. Describe only observed values,
variability, timing and explicit confounders in the fact sheet. Do not diagnose,
infer causation, prescribe treatment, provide medical advice, invent values, or call
a value beneficial or harmful. End with the supplied disclaimer verbatim."""


def normalize_research_narration(value: Any) -> str:
    return "\n".join(
        line.strip() for line in str(value or "").splitlines() if line.strip()
    )[:RESEARCH_MAX_NARRATION_CHARACTERS]


def valid_research_narration(text: str, facts: dict[str, Any]) -> bool:
    normalized = text.lower()
    headings = (
        "abstract",
        "methods",
        "observations",
        "interpretation",
        "limitations",
        "future data required",
    )
    forbidden = ("diagnoza", "rozpoznanie", "leczenie", "lek ", "choroba")
    return bool(
        text
        and len(text) <= RESEARCH_MAX_NARRATION_CHARACTERS
        and all(heading in normalized for heading in headings)
        and text.endswith(facts["disclaimer"])
        and not any(term in normalized for term in forbidden)
    )
