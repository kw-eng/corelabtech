"""Trend and baseline calculations for physiological sessions.

The functions in this module are pure and database-agnostic on purpose. Routes
or repositories can feed them rows from PostgreSQL, CSV exports, or tests.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
from statistics import mean
from typing import Any


def numeric_values(
    rows: Iterable[dict[str, Any]],
    key: str,
) -> list[float]:
    values: list[float] = []

    for row in rows:
        value = row.get(key)

        if value is None:
            continue

        try:
            values.append(float(value))
        except (TypeError, ValueError):
            continue

    return values


def average(values: Iterable[float]) -> float | None:
    clean = list(values)

    return round(mean(clean), 2) if clean else None


def minimum(values: Iterable[float]) -> float | None:
    clean = list(values)

    return min(clean) if clean else None


def rolling_average(
    rows: list[dict[str, Any]],
    *,
    value_key: str,
    date_key: str = "date",
    end_date: date | None = None,
    days: int = 7,
) -> float | None:
    """Return an average for rows inside a trailing day window."""

    if days <= 0:
        raise ValueError("days must be positive")

    normalized = [
        row
        for row in rows
        if parse_date(row.get(date_key)) is not None
    ]

    if not normalized:
        return None

    final_date = end_date or max(
        parse_date(row.get(date_key))
        for row in normalized
        if parse_date(row.get(date_key)) is not None
    )

    if final_date is None:
        return None

    window = [
        row
        for row in normalized
        if 0 <= (final_date - parse_date(row.get(date_key))).days < days
    ]

    return average(numeric_values(window, value_key))


def build_daily_baseline(
    rows: list[dict[str, Any]],
    *,
    user_id: str,
    baseline_date: date | None = None,
) -> dict[str, Any]:
    """Build a baseline summary from daily/session feature rows."""

    final_date = baseline_date or infer_latest_date(rows)

    rmssd_values = numeric_values(rows, "rmssd")
    hr_values = numeric_values(rows, "avg_hr")
    spo2_values = numeric_values(rows, "avg_spo2")
    spo2_min_values = numeric_values(rows, "min_spo2")
    quality_values = numeric_values(rows, "data_quality_score")

    return {
        "user_id": user_id,
        "baseline_date": final_date.isoformat() if final_date else None,
        "rmssd_avg": average(rmssd_values),
        "rmssd_7d": rolling_average(
            rows,
            value_key="rmssd",
            end_date=final_date,
            days=7,
        ),
        "rmssd_14d": rolling_average(
            rows,
            value_key="rmssd",
            end_date=final_date,
            days=14,
        ),
        "rmssd_30d": rolling_average(
            rows,
            value_key="rmssd",
            end_date=final_date,
            days=30,
        ),
        "resting_hr": minimum(hr_values),
        "resting_hr_7d": rolling_average(
            rows,
            value_key="avg_hr",
            end_date=final_date,
            days=7,
        ),
        "spo2_avg": average(spo2_values),
        "spo2_min": minimum(spo2_min_values),
        "sessions_count_7d": count_window(rows, end_date=final_date, days=7),
        "sessions_count_14d": count_window(rows, end_date=final_date, days=14),
        "sessions_count_30d": count_window(rows, end_date=final_date, days=30),
        "data_quality_score": average(quality_values),
    }


def trend_direction(
    current: float | None,
    baseline: float | None,
    *,
    tolerance_ratio: float = 0.05,
) -> str:
    if current is None or baseline in (None, 0):
        return "unknown"

    delta_ratio = (current - baseline) / abs(baseline)

    if abs(delta_ratio) <= tolerance_ratio:
        return "stable"

    return "up" if delta_ratio > 0 else "down"


def count_window(
    rows: list[dict[str, Any]],
    *,
    end_date: date | None,
    days: int,
) -> int:
    if end_date is None:
        return 0

    return sum(
        1
        for row in rows
        if (
            parse_date(row.get("date")) is not None
            and 0 <= (end_date - parse_date(row.get("date"))).days < days
        )
    )


def infer_latest_date(rows: list[dict[str, Any]]) -> date | None:
    dates = [
        parsed
        for row in rows
        if (parsed := parse_date(row.get("date"))) is not None
    ]

    return max(dates) if dates else None


def parse_date(value: Any) -> date | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    text = str(value).strip()

    if not text:
        return None

    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None
