# services/csv_parser.py

from pathlib import Path
from typing import Any

import pandas as pd


# =========================================================
# SAFE CONVERSIONS
# =========================================================

def safe_float(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None

        return float(value)

    except (TypeError, ValueError):
        return None


def safe_int(value: Any) -> int | None:
    number = safe_float(value)

    if number is None:
        return None

    return int(number)


# =========================================================
# NORMALIZE COLUMN
# =========================================================

def normalize_column(name: Any) -> str:
    return (
        str(name)
        .strip()
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
        .replace("/", "_")
    )


# =========================================================
# FIND FIRST AVAILABLE COLUMN
# =========================================================

def find_column(
    columns: list[str],
    aliases: list[str],
) -> str | None:
    for alias in aliases:
        if alias in columns:
            return alias

    return None


# =========================================================
# CSV PARSER
# =========================================================

def parse_csv_file(path: str | Path) -> list[dict]:
    try:
        df = pd.read_csv(
            path,
            encoding="utf-8-sig",
        )

    except UnicodeDecodeError:
        df = pd.read_csv(
            path,
            encoding="cp1252",
        )

    except Exception as exc:
        raise ValueError(f"CSV read error: {exc}") from exc

    if df.empty:
        raise ValueError("CSV file contains no records")

    df.columns = [
        normalize_column(column)
        for column in df.columns
    ]

    columns = df.columns.tolist()

    timestamp_column = find_column(
        columns,
        [
            "timestamp",
            "time",
            "datetime",
            "date_time",
            "date",
        ],
    )

    pulse_column = find_column(
        columns,
        [
            "pulse",
            "pulse_rate",
            "heart_rate",
            "hr",
            "bpm",
            "pr",
            "pr_bpm",
        ],
    )

    spo2_column = find_column(
        columns,
        [
            "spo2",
            "sp02",
            "s02",
            "so2",
            "spo₂",
            "oxygen",
            "oxygen_level",
            "oxygen_saturation",
            "saturation",
            "blood_oxygen",
            "o2",
            "sat",
        ],
    )

    motion_column = find_column(
        columns,
        [
            "motion",
            "movement",
            "activity",
        ],
    )

    o2_reminder_column = find_column(
        columns,
        [
            "o2_reminder",
            "spo2_reminder",
            "oxygen_reminder",
        ],
    )

    pr_reminder_column = find_column(
        columns,
        [
            "pr_reminder",
            "pulse_reminder",
            "heart_rate_reminder",
        ],
    )

    missing = []

    if timestamp_column is None:
        missing.append("timestamp")

    if spo2_column is None:
        missing.append("SpO2")

    if pulse_column is None:
        missing.append("pulse")

    if missing:
        raise ValueError(
            "Required CSV columns were not found: "
            + ", ".join(missing)
            + f". Available columns: {columns}"
        )

    rows: list[dict] = []

    for index, record in df.iterrows():
        raw_timestamp = record[timestamp_column]

        timestamp = pd.to_datetime(
            raw_timestamp,
            format="%H:%M:%S %b %d %Y",
            errors="coerce",
        )

        if pd.isna(timestamp):
            timestamp = pd.to_datetime(
                raw_timestamp,
                errors="coerce",
            )

        if pd.isna(timestamp):
            continue

        spo2 = safe_float(record[spo2_column])
        pulse = safe_float(record[pulse_column])

        if spo2 is None and pulse is None:
            continue

        if spo2 is not None and not 50 <= spo2 <= 100:
            continue

        if pulse is not None and not 20 <= pulse <= 250:
            continue

        row = {
            "timestamp": timestamp.isoformat(),
            "pulse": pulse,
            "heart_rate": pulse,
            "spo2": spo2,
            "motion": (
                safe_int(record[motion_column])
                if motion_column
                else None
            ),
            "o2_reminder": (
                safe_int(record[o2_reminder_column])
                if o2_reminder_column
                else None
            ),
            "pr_reminder": (
                safe_int(record[pr_reminder_column])
                if pr_reminder_column
                else None
            ),
            "source": "pulseox",
            "device": "checkme_o2",
        }

        rows.append(row)

    if not rows:
        raise ValueError(
            "No valid SpO2 or pulse measurements were found in the CSV file"
        )

    return rows