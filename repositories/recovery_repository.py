"""Persistence helpers for voluntary post-session recovery follow-ups."""

from __future__ import annotations

from typing import Any


_ALLOWED_LEVELS = {
    "energy_level": {"lower", "same", "higher"},
    "fatigue_level": {"lower", "same", "higher"},
    "sleep_quality": {"poor", "fair", "good"},
    "discomfort": {"none", "mild", "moderate"},
}
_ALLOWED_WINDOWS = {"one_hour", "next_day"}


def normalize_recovery_follow_up_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Accept only the bounded, voluntary wellness follow-up contract."""

    normalized: dict[str, Any] = {}
    window = payload.get("follow_up_window") or "one_hour"
    if not isinstance(window, str) or window not in _ALLOWED_WINDOWS:
        raise ValueError("invalid follow_up_window")
    normalized["follow_up_window"] = window
    for field, allowed_values in _ALLOWED_LEVELS.items():
        value = payload.get(field)
        if value in (None, ""):
            normalized[field] = None
            continue
        if not isinstance(value, str) or value not in allowed_values:
            raise ValueError(f"invalid {field}")
        normalized[field] = value

    for field, minimum, maximum in (
        ("heart_rate_bpm", 20, 250),
        ("spo2", 50, 100),
    ):
        value = payload.get(field)
        if value in (None, ""):
            normalized[field] = None
            continue
        if isinstance(value, bool):
            raise ValueError(f"invalid {field}")
        try:
            numeric_value = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid {field}") from exc
        if not minimum <= numeric_value <= maximum:
            raise ValueError(f"invalid {field}")
        normalized[field] = round(numeric_value, 1)

    return normalized


def create_recovery_follow_up(
    cursor,
    *,
    session_id: str,
    user_id: str,
    payload: dict[str, Any],
) -> int:
    cursor.execute(
        """
        INSERT INTO recovery_follow_ups (
            session_id, user_id, follow_up_window, energy_level, fatigue_level, sleep_quality,
            discomfort, heart_rate_bpm, spo2
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            session_id,
            user_id,
            payload.get("follow_up_window"),
            payload.get("energy_level"),
            payload.get("fatigue_level"),
            payload.get("sleep_quality"),
            payload.get("discomfort"),
            payload.get("heart_rate_bpm"),
            payload.get("spo2"),
        ),
    )
    return cursor.fetchone()[0]


def load_latest_recovery_follow_ups(cursor, *, session_id: str) -> dict[str, dict[str, Any]]:
    """Return the newest voluntary entry for each supported follow-up window."""

    cursor.execute(
        """
        SELECT DISTINCT ON (follow_up_window)
            follow_up_window,
            energy_level,
            fatigue_level,
            sleep_quality,
            discomfort,
            heart_rate_bpm,
            spo2,
            recorded_at
        FROM recovery_follow_ups
        WHERE session_id = %s
          AND follow_up_window IN ('one_hour', 'next_day')
        ORDER BY follow_up_window, recorded_at DESC, id DESC
        """,
        (session_id,),
    )
    return {
        row[0]: {
            "follow_up_window": row[0],
            "energy_level": row[1],
            "fatigue_level": row[2],
            "sleep_quality": row[3],
            "discomfort": row[4],
            "heart_rate_bpm": row[5],
            "spo2": row[6],
            "recorded_at": row[7],
        }
        for row in cursor.fetchall()
    }


def load_recovery_follow_up_history(
    cursor,
    *,
    user_id: str,
    exclude_session_id: str,
    limit: int = 30,
) -> list[dict[str, Any]]:
    """Load a bounded personal recovery history, never population data."""

    cursor.execute(
        """
        WITH latest_per_session_window AS (
            SELECT DISTINCT ON (session_id, follow_up_window)
                session_id,
                follow_up_window,
                energy_level,
                fatigue_level,
                sleep_quality,
                discomfort,
                heart_rate_bpm,
                spo2,
                recorded_at
            FROM recovery_follow_ups
            WHERE user_id = %s
              AND session_id <> %s
              AND follow_up_window IN ('one_hour', 'next_day')
            ORDER BY session_id, follow_up_window, recorded_at DESC, id DESC
        )
        SELECT
            session_id,
            follow_up_window,
            energy_level,
            fatigue_level,
            sleep_quality,
            discomfort,
            heart_rate_bpm,
            spo2,
            recorded_at
        FROM latest_per_session_window
        ORDER BY recorded_at DESC
        LIMIT %s
        """,
        (user_id, exclude_session_id, limit * 2),
    )
    return [
        {
            "session_id": row[0],
            "follow_up_window": row[1],
            "energy_level": row[2],
            "fatigue_level": row[3],
            "sleep_quality": row[4],
            "discomfort": row[5],
            "heart_rate_bpm": row[6],
            "spo2": row[7],
            "recorded_at": row[8],
        }
        for row in cursor.fetchall()
    ]
