"""Optional LLM narration over a minimized, versioned analysis fact sheet."""

from __future__ import annotations

import json
import os
from time import perf_counter
from dataclasses import asdict, dataclass
from typing import Any

from services.llm_observability import record_llm_event
from services.wellness_response import build_session_response


FACT_SHEET_VERSION = "wellness-fact-sheet-v3"
NARRATION_VERSION = "llm-narration-v2"
DEFAULT_MODEL = "gpt-5-mini"
MAX_NARRATION_CHARACTERS = 1200
REQUIRED_HEADINGS = (
    "ograniczenia danych",
    "podsumowanie",
    "check-in",
    "przebieg sesji",
    "check-out",
    "jakosc sesji",
)
FORBIDDEN_MEDICAL_TERMS = (
    "diagnoza",
    "rozpoznanie",
    "leczenie",
    "lek ",
    "choroba",
)


@dataclass(frozen=True)
class NarrationResult:
    text: str
    status: str
    provider: str | None
    model: str | None
    narration_version: str
    fact_sheet_version: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_session_fact_sheet(analysis: dict[str, Any]) -> dict[str, Any]:
    """Select only non-identifying, computed facts for LLM narration."""

    features = analysis.get("features") or {}
    context = features.get("session_context") or analysis.get("session_context") or {}
    history = analysis.get("wellness_history") or {}
    pre_check_in = select_fields(
        context.get("pre_check_in") or {},
        "spo2", "avg_spo2", "pulse", "heart_rate_bpm", "heart_rate",
        "sleep_hours", "sleep_quality", "training_load_24h", "stress_level",
        "fatigue_level", "session_goal",
    )
    post_check_out = select_fields(
        context.get("post_check_out") or {},
        "spo2", "avg_spo2", "pulse", "heart_rate_bpm", "heart_rate",
        "energy_level", "relaxation_level", "fatigue_level", "discomfort",
    )
    protocol = analysis.get("protocol") or {}
    timing = context.get("session_timing") or {}
    session_response = analysis.get("session_response") or build_session_response(
        session_context=context,
        features=features,
        data_quality_score=analysis.get("data_quality_score"),
        analysis_confidence=analysis.get("analysis_confidence"),
        quality_warnings=analysis.get("quality_warnings") or [],
    )
    return {
        "schema_version": FACT_SHEET_VERSION,
        "analysis_model": {
            "name": analysis.get("model_name"),
            "version": analysis.get("model_version"),
        },
        "hrv": {
            "algorithm_version": features.get("hrv_algorithm_version"),
            "confidence": features.get("hrv_confidence"),
            "rr_count": features.get("rr_count"),
            "artifact_ratio": features.get("artifact_ratio"),
            "rmssd": features.get("avg_hrv"),
        },
        "data_quality": {
            "score": analysis.get("data_quality_score"),
            "analysis_confidence": analysis.get("analysis_confidence"),
            "signal_quality": features.get("signal_quality"),
            "limitations": analysis.get("quality_warnings") or [],
            "quality_reasons": features.get("quality_reasons") or [],
        },
        "measurements": {
            "avg_spo2": features.get("avg_spo2"),
            "min_spo2": features.get("min_spo2"),
            "avg_reference_heart_rate": features.get("avg_reference_heart_rate"),
            "max_reference_heart_rate": features.get("max_reference_heart_rate"),
            "avg_pulse": features.get("avg_pulse"),
            "hr_pulse_agreement_percent": features.get("hr_pulse_agreement_percent"),
        },
        "check_in": pre_check_in,
        "check_out": post_check_out,
        "session_response": session_response,
        "protocol": {
            "code": protocol.get("code"),
            "name": protocol.get("name"),
            "mode": protocol.get("mode"),
            "version": protocol.get("version"),
            "target_ata": context.get("target_ata"),
            "actual_ata": context.get("actual_ata"),
            "pressure_deviation": context.get("pressure_deviation"),
            "execution_status": context.get("execution_status"),
            "timing": select_fields(
                timing,
                "compression_time_min", "exposure_time_min", "decompression_time_min", "total_duration_min",
            ),
            "segments": [
                select_fields(segment, "phase", "actual_duration_min", "target_ata", "actual_ata", "oxygen_mode")
                for segment in context.get("segments") or []
            ],
        },
        "history": {
            "baseline_confidence": history.get("baseline_confidence"),
            "unique_sessions_30d": history.get("unique_sessions_30d"),
            "baseline": select_fields(
                history.get("baseline") or {},
                "rmssd_30d", "resting_hr", "spo2_avg", "spo2_min", "data_quality_score", "status",
            ),
        },
        "session_comparison": analysis.get("session_comparison") or {},
        "recovery_follow_up": select_fields(
            context.get("recovery_follow_up") or {},
            "follow_up_window", "energy_level", "fatigue_level", "sleep_quality", "discomfort", "heart_rate_bpm", "spo2",
        ),
        "recovery_follow_ups": {
            window: select_fields(
                entry or {},
                "follow_up_window", "energy_level", "fatigue_level", "sleep_quality", "discomfort", "heart_rate_bpm", "spo2",
            )
            for window, entry in (context.get("recovery_follow_ups") or {}).items()
        },
        "availability": {
            "check_in": bool(pre_check_in),
            "check_out": bool(post_check_out),
            "protocol": bool(protocol or timing),
            "history": bool(history.get("recent_sessions")),
        },
        "wellness": {
            "score": analysis.get("wellness_response_score"),
            "status": analysis.get("wellness_status"),
            "flags": analysis.get("wellness_flags") or {},
        },
        "session_quality": analysis.get("session_quality") or {},
        "disclaimer": analysis.get("wellness_disclaimer"),
    }


def narrate_fact_sheet(
    fact_sheet: dict[str, Any],
) -> NarrationResult:
    """Generate a short Polish report narrative only when explicitly enabled."""

    fallback = deterministic_fallback(fact_sheet)
    if not enabled():
        return NarrationResult(
            text=fallback,
            status="disabled",
            provider=None,
            model=None,
            narration_version=NARRATION_VERSION,
            fact_sheet_version=FACT_SHEET_VERSION,
        )

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return NarrationResult(
            text=fallback,
            status="missing_api_key",
            provider="openai",
            model=os.getenv("OPENAI_MODEL", DEFAULT_MODEL),
            narration_version=NARRATION_VERSION,
            fact_sheet_version=FACT_SHEET_VERSION,
        )

    started_at = perf_counter()
    model = os.getenv("OPENAI_MODEL", DEFAULT_MODEL)
    try:
        from openai import OpenAI

        response = OpenAI(api_key=api_key).responses.create(
            model=model,
            instructions=narration_instructions(),
            input=json.dumps(fact_sheet, ensure_ascii=True),
            max_output_tokens=350,
            store=False,
        )
        text = normalize_narration(getattr(response, "output_text", ""))
        if not narration_is_valid(text, fact_sheet):
            raise ValueError("LLM narration failed the output policy")
        record_llm_event(
            feature="session_summary",
            status="generated",
            provider="openai",
            model=model,
            started_at=started_at,
            response=response,
        )
        return NarrationResult(
            text=text,
            status="generated",
            provider="openai",
            model=model,
            narration_version=NARRATION_VERSION,
            fact_sheet_version=FACT_SHEET_VERSION,
        )
    except Exception as exc:
        record_llm_event(
            feature="session_summary",
            status="fallback_after_provider_error",
            provider="openai",
            model=model,
            started_at=started_at,
            error=exc,
        )
        return NarrationResult(
            text=fallback,
            status="fallback_after_provider_error",
            provider="openai",
            model=model,
            narration_version=NARRATION_VERSION,
            fact_sheet_version=FACT_SHEET_VERSION,
        )


def narration_instructions() -> str:
    return """You are CoreLabTech Session Summary AI. Write a concise Polish wellness
report using only the supplied versioned JSON fact sheet. Use exactly these headings:
Ograniczenia danych, Podsumowanie, Check-in, Przebieg sesji, Check-out, Jakosc sesji.
Start with data limitations and analysis confidence. Keep Podsumowanie under 100 words.
Describe only available pre-session, during-session and recovery facts; do not invent
values or infer causes. If a section is unavailable, state exactly: 'Brak danych do
oceny tej czesci sesji.' Do not diagnose, predict disease, prescribe treatment, make
medical advice, or make recommendations. Do not change the wellness score. Treat
HR-versus-PPG disagreement as data quality, not a physiological finding. End with the
supplied disclaimer verbatim."""


def deterministic_fallback(fact_sheet: dict[str, Any]) -> str:
    """Keep reports available without sending telemetry to an LLM provider."""

    quality = fact_sheet["data_quality"]
    limitations = quality.get("limitations") or quality.get("quality_reasons") or []
    limitation_text = ", ".join(str(item) for item in limitations) or "brak zgłoszonych ograniczeń"
    status = fact_sheet["wellness"].get("status") or "brak oceny"
    unavailable = "Brak danych do oceny tej czesci sesji."
    return "\n\n".join(
        [
            f"Ograniczenia danych\n{limitation_text}. Pewnosc analizy: {quality.get('analysis_confidence') or 'unknown'}.",
            f"Podsumowanie\nDeterministyczna ocena wellness ma status: {status}.",
            f"Check-in\n{unavailable}",
            f"Przebieg sesji\n{unavailable}",
            f"Check-out\n{unavailable}",
            f"Jakosc sesji\n{quality.get('signal_quality') or 'unknown'}.",
            str(fact_sheet.get("disclaimer") or ""),
        ]
    ).strip()


def localized_deterministic_summary(
    fact_sheet: dict[str, Any], catalog: dict[str, str]
) -> str:
    """Render dashboard narration from current facts in the active locale.

    Persisted LLM/fallback narration has no locale contract.  The dashboard uses
    this renderer so its deterministic text is reproducible from the selected
    locale and cannot reuse a Polish summary in an English session.
    """

    def text(key: str, **params: Any) -> str:
        value = catalog.get(key, key)
        return value.format(**params) if params else value

    def enum(value: Any) -> str:
        if value in (None, ""):
            return text("report.session_summary_unavailable")
        raw = str(value).strip().lower()
        return catalog.get(f"report.context_value_{raw}", str(value))

    def warning(value: Any) -> str:
        key = f"report.warning_{str(value).strip().lower()}"
        return catalog.get(key) or text("report.warning_unclassified")

    def wellness_status(value: Any) -> str:
        raw = str(value or "unknown").strip().lower()
        return catalog.get(
            f"report.wellness_status_{raw}",
            text("report.session_summary_unavailable"),
        )

    def measurement(value: Any, unit: str = "") -> str:
        return f"{value}{unit}" if value not in (None, "") else ""

    def context_values(values: dict[str, Any], fields: tuple[tuple[str, str, str], ...]) -> str:
        rendered = []
        for field, label_key, unit in fields:
            value = values.get(field)
            if value in (None, ""):
                continue
            display = measurement(value, unit) if unit else enum(value)
            rendered.append(f"{text(label_key)}: {display}")
        return "; ".join(rendered) or text("report.session_summary_unavailable")

    quality = fact_sheet.get("data_quality") or {}
    limitations = quality.get("limitations") or quality.get("quality_reasons") or []
    limitation_text = ", ".join(
        warning(item) for item in limitations
    ) or text("report.session_summary_no_limitations")
    check_in = context_values(
        fact_sheet.get("check_in") or {},
        (
            ("spo2", "report.context_spo2", "%"),
            ("avg_spo2", "report.context_spo2", "%"),
            ("pulse", "report.context_pulse_hr", " bpm"),
            ("heart_rate_bpm", "report.context_pulse_hr", " bpm"),
            ("heart_rate", "report.context_pulse_hr", " bpm"),
            ("sleep_hours", "report.context_sleep_hours", " h"),
            ("sleep_quality", "report.context_sleep_quality", ""),
            ("stress_level", "report.context_stress_level", ""),
            ("training_load_24h", "report.context_training_load_24h", ""),
            ("fatigue_level", "report.context_fatigue_level", ""),
            ("session_goal", "report.context_session_goal", ""),
        ),
    )
    check_out = context_values(
        fact_sheet.get("check_out") or {},
        (
            ("spo2", "report.context_spo2", "%"),
            ("avg_spo2", "report.context_spo2", "%"),
            ("pulse", "report.context_pulse_hr", " bpm"),
            ("heart_rate_bpm", "report.context_pulse_hr", " bpm"),
            ("heart_rate", "report.context_pulse_hr", " bpm"),
            ("energy_level", "report.context_energy_level", ""),
            ("relaxation_level", "report.context_relaxation_level", ""),
            ("fatigue_level", "report.context_fatigue_level", ""),
            ("discomfort", "report.context_discomfort", ""),
        ),
    )
    timing = (fact_sheet.get("protocol") or {}).get("timing") or {}
    phases = []
    for field, label_key in (
        ("compression_time_min", "report.phase_compression"),
        ("exposure_time_min", "report.phase_exposure"),
        ("decompression_time_min", "report.phase_decompression"),
        ("total_duration_min", "report.label_duration"),
    ):
        if timing.get(field) not in (None, ""):
            phases.append(f"{text(label_key)}: {measurement(timing[field], ' min')}")
    phase_text = "; ".join(phases) or text("report.session_summary_unavailable")
    status = wellness_status((fact_sheet.get("wellness") or {}).get("status"))
    return "\n\n".join(
        (
            f"{text('report.session_summary_limitations')}\n{limitation_text}. "
            f"{text('report.session_summary_confidence')}: {enum(quality.get('analysis_confidence'))}.",
            f"{text('report.session_summary_overview')}\n"
            f"{text('report.session_summary_wellness_status')}: {status}.",
            f"{text('report.session_summary_check_in')}\n{check_in}",
            f"{text('report.session_summary_during')}\n{phase_text}",
            f"{text('report.session_summary_check_out')}\n{check_out}",
            f"{text('report.session_summary_quality')}\n"
            f"{text('report.session_summary_signal_quality')}: {enum(quality.get('signal_quality'))}.",
            text("analysis.wellness_educational_disclaimer"),
        )
    ).strip()


def normalize_narration(text: Any) -> str:
    normalized = "\n".join(
        line.strip()
        for line in str(text or "").splitlines()
        if line.strip()
    )
    return normalized[:MAX_NARRATION_CHARACTERS]


def narration_is_valid(text: str, fact_sheet: dict[str, Any]) -> bool:
    """Reject a narration that misses required structure or safety guardrails."""

    normalized = text.lower()
    disclaimer = str(fact_sheet.get("disclaimer") or "").strip()
    return bool(
        text
        and len(text) <= MAX_NARRATION_CHARACTERS
        and all(heading in normalized for heading in REQUIRED_HEADINGS)
        and (not disclaimer or text.endswith(disclaimer))
        and not any(term in normalized for term in FORBIDDEN_MEDICAL_TERMS)
    )


def enabled() -> bool:
    return os.getenv("LLM_NARRATION_ENABLED", "false").strip().lower() == "true"


def select_fields(source: dict[str, Any], *fields: str) -> dict[str, Any]:
    """Keep the LLM payload explicit and free of arbitrary form fields."""

    return {
        field: source.get(field)
        for field in fields
        if source.get(field) not in (None, "")
    }
