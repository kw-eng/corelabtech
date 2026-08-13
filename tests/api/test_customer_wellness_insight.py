import json
from pathlib import Path

from services.customer_wellness_insight import (
    build_series_customer_insight,
    build_session_customer_insight,
)
from services.session_service import series_comparison_measurement_rows


def catalog(locale):
    return json.loads(Path(f"translations/{locale}.json").read_text(encoding="utf-8"))


def response_presentation():
    return {
        "confidence": "Moderate",
        "deltas": [{"label": "Heart rate", "before": "70 bpm", "after": "68 bpm", "delta": "-2 bpm"}],
        "subjective": [{"label": "Energy", "value": "Higher"}],
        "observations": ["Post-session heart rate was lower."],
        "limitations": ["HRV comparison is unavailable for this session."],
    }


def test_session_customer_insight_uses_existing_presentation_facts_without_codes():
    insight = build_session_customer_insight(
        analysis={"result": {"wellness_status": "stable"}},
        response_presentation=response_presentation(),
        catalog=catalog("en"),
    )

    assert insight["status"] == "Stable response"
    assert insight["changes"][0]["delta"] == "-2 bpm"
    assert "Energy: Higher" in insight["summary"]
    assert "sensor_alignment_warning" not in str(insight)


def test_polish_session_customer_insight_is_localized_and_keeps_missing_data_as_watch_item():
    insight = build_session_customer_insight(
        analysis={"result": {"wellness_status": "data_quality_warning"}},
        response_presentation={**response_presentation(), "confidence": "Umiarkowana"},
        catalog=catalog("pl"),
    )

    assert insight["headline"] == "Wnioski z Twojej sesji"
    assert insight["status"] == "Interpretuj ostrożnie"
    assert "HRV comparison is unavailable" in insight["watch_items"][0]


def test_series_customer_insight_reframes_preliminary_evidence_as_personal_pattern():
    insight = build_series_customer_insight(
        series_data={
            "records": 3,
            "trend_direction": "stable",
            "evidence_level": "preliminary",
            "data_quality_engine": {"warning_counts": {"sensor_alignment_warning": 1}},
        },
        catalog=catalog("en"),
    )

    assert insight["status"] == "Stable pattern"
    assert "longitudinal evidence" not in insight["summary"].lower()
    assert "sensor_alignment_warning" not in str(insight)
    assert insight["confidence"] == "Moderate"
    assert "(s)" not in insight["watch_items"][0]


def test_polish_series_customer_insight_uses_natural_pattern_language():
    insight = build_series_customer_insight(
        series_data={"records": 3, "trend_direction": "stable", "evidence_level": "preliminary"},
        catalog=catalog("pl"),
    )

    assert "W 3 przeanalizowanych sesjach" in insight["summary"]
    assert "indywidualny wzorzec" in insight["pattern"]


def test_series_comparison_omits_measurements_without_two_real_endpoints():
    rows = series_comparison_measurement_rows(
        {
            "first_avg_heart_rate": None,
            "last_avg_heart_rate": None,
            "first_avg_hrv": 42.0,
            "last_avg_hrv": 44.0,
            "hrv_delta": 2.0,
            "first_avg_spo2": None,
            "last_avg_spo2": 98.0,
        },
        catalog("en"),
    )

    assert rows == [("Average HRV", "42 ms -> 44 ms (+2)")]
