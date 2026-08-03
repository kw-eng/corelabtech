"""Timestamp preservation and UTC normalization for telemetry imports."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


UNKNOWN_TIMEZONE = "unknown"


def normalize_rows_timestamps(
    rows: list[dict[str, Any]],
    *,
    source_timezone: str | None,
) -> list[dict[str, Any]]:
    """Attach original time and UTC time when the source timezone is known."""

    for row in rows:
        original_timestamp = str(
            row.get("original_timestamp") or row.get("timestamp") or ""
        )
        parsed = parse_timestamp(row.get("timestamp"))
        timezone_name = normalize_timezone_name(source_timezone, parsed)

        row["original_timestamp"] = original_timestamp or None
        row["source_timezone"] = timezone_name
        row["timestamp_utc"] = to_utc(parsed, timezone_name)

    return rows


def parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def normalize_timezone_name(
    source_timezone: str | None,
    parsed: datetime | None,
) -> str:
    if parsed and parsed.tzinfo is not None:
        return str(parsed.tzinfo)
    if not source_timezone:
        return UNKNOWN_TIMEZONE
    try:
        ZoneInfo(source_timezone)
    except ZoneInfoNotFoundError:
        return UNKNOWN_TIMEZONE
    return source_timezone


def to_utc(
    parsed: datetime | None,
    timezone_name: str,
) -> datetime | None:
    if parsed is None or timezone_name == UNKNOWN_TIMEZONE:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(timezone_name))
    return parsed.astimezone(timezone.utc)
