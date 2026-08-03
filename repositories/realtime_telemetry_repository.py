"""Session-scoped persistence for bounded live telemetry measurements."""

from __future__ import annotations

from typing import Any


_NUMERIC_FIELDS = {
    "heart_rate_bpm": ("heart_rate_bpm", 20.0, 250.0),
    "pulse_rate_bpm": ("pulse_rate_bpm", 20.0, 250.0),
    "pulse": ("pulse_rate_bpm", 20.0, 250.0),
    "spo2": ("spo2", 50.0, 100.0),
    "pressure_ata": ("pressure_ata", 0.8, 3.0),
    "ata": ("pressure_ata", 0.8, 3.0),
    "chamber_temperature_c": ("chamber_temperature_c", 5.0, 50.0),
    "temperature": ("chamber_temperature_c", 5.0, 50.0),
}
_SOURCE_TYPES = {"chest_hrm", "finger_oximeter", "watch_ppg", "unknown"}
_MEASUREMENT_METHODS = {"ecg", "ppg", "unknown"}
_SIGNAL_QUALITIES = {"high", "medium", "low", "unknown"}


def normalize_realtime_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Accept only bounded live measurements; HRV needs the offline RR pipeline."""

    if not isinstance(payload, dict):
        raise ValueError("realtime telemetry payload must be an object")

    normalized: dict[str, Any] = {
        "source_type": normalize_choice(payload.get("source_type"), _SOURCE_TYPES),
        "measurement_method": normalize_choice(
            payload.get("measurement_method"), _MEASUREMENT_METHODS
        ),
        "signal_quality": normalize_choice(
            payload.get("signal_quality"), _SIGNAL_QUALITIES
        ),
    }
    for source_key, (target_key, minimum, maximum) in _NUMERIC_FIELDS.items():
        if source_key not in payload or normalized.get(target_key) is not None:
            continue
        normalized[target_key] = normalize_number(
            payload[source_key], field=source_key, minimum=minimum, maximum=maximum
        )

    if not any(
        normalized.get(key) is not None
        for key in (
            "heart_rate_bpm",
            "pulse_rate_bpm",
            "spo2",
            "pressure_ata",
            "chamber_temperature_c",
        )
    ):
        raise ValueError("at least one realtime measurement is required")
    return normalized


def normalize_choice(value: Any, allowed: set[str]) -> str:
    if value in (None, ""):
        return "unknown"
    normalized = str(value).strip().lower()
    if normalized not in allowed:
        raise ValueError("invalid realtime telemetry metadata")
    return normalized


def normalize_number(value: Any, *, field: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool):
        raise ValueError(f"invalid {field}")
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid {field}") from exc
    if not minimum <= numeric <= maximum:
        raise ValueError(f"invalid {field}")
    return round(numeric, 2)


def create_realtime_event(
    cursor,
    *,
    session_id: str,
    client_id: str,
    organization_id: int | None,
    location_id: int | None,
    recorded_by_user_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    cursor.execute(
        """
        INSERT INTO realtime_telemetry_events (
            session_id, client_id, organization_id, location_id, recorded_by_user_id,
            heart_rate_bpm, pulse_rate_bpm, spo2, pressure_ata,
            chamber_temperature_c, source_type, measurement_method, signal_quality
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id, recorded_at
        """,
        (
            session_id,
            client_id,
            organization_id,
            location_id,
            recorded_by_user_id,
            payload.get("heart_rate_bpm"),
            payload.get("pulse_rate_bpm"),
            payload.get("spo2"),
            payload.get("pressure_ata"),
            payload.get("chamber_temperature_c"),
            payload["source_type"],
            payload["measurement_method"],
            payload["signal_quality"],
        ),
    )
    event_id, recorded_at = cursor.fetchone()
    return {"id": event_id, "recorded_at": recorded_at}


def get_realtime_session_context(cursor, *, session_id: str) -> dict[str, Any] | None:
    cursor.execute(
        """
        SELECT client_id, organization_id, location_id
        FROM realtime_telemetry_events
        WHERE session_id = %s
        ORDER BY recorded_at DESC, id DESC
        LIMIT 1
        """,
        (session_id,),
    )
    row = cursor.fetchone()
    if not row:
        return None
    return {"client_id": row[0], "organization_id": row[1], "location_id": row[2]}


def list_realtime_events(cursor, *, session_id: str, limit: int = 300) -> list[dict[str, Any]]:
    cursor.execute(
        """
        SELECT id, recorded_at, heart_rate_bpm, pulse_rate_bpm, spo2, pressure_ata,
               chamber_temperature_c, source_type, measurement_method, signal_quality
        FROM realtime_telemetry_events
        WHERE session_id = %s
        ORDER BY recorded_at DESC, id DESC
        LIMIT %s
        """,
        (session_id, limit),
    )
    rows = list(reversed(cursor.fetchall()))
    return [
        {
            "id": row[0],
            "recorded_at": row[1].isoformat() if row[1] else None,
            "heart_rate_bpm": row[2],
            "pulse_rate_bpm": row[3],
            "spo2": row[4],
            "pressure_ata": row[5],
            "chamber_temperature_c": row[6],
            "source_type": row[7],
            "measurement_method": row[8],
            "signal_quality": row[9],
        }
        for row in rows
    ]
