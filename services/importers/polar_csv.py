"""Conservative Polar CSV importer for heart-rate and optional RR exports."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from core.telemetry.contract import canonicalize_telemetry_rows


def normalized_key(value: str) -> str:
    return value.strip().lower().replace(" ", "_").replace("-", "_")


def first_value(record: dict[str, str], aliases: tuple[str, ...]) -> str | None:
    for alias in aliases:
        value = record.get(alias)
        if value not in (None, ""):
            return value
    return None


def number(value: Any) -> float | None:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def rr_values(value: str | None) -> list[float]:
    if not value:
        return []
    values = []
    for item in value.replace(";", ",").split(","):
        parsed = number(item)
        if parsed is None:
            continue
        values.append(parsed * 1000 if 0 < parsed < 10 else parsed)
    return values


class PolarCsvImporter:
    """Import common Polar CSV column aliases without guessing a device model."""

    import_type = "polar_csv"
    parser_version = "polar-csv-v1"

    def import_data(self, path: str | Path) -> list[dict[str, Any]]:
        with open(path, encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source)
            if not reader.fieldnames:
                raise ValueError("Polar CSV has no header")
            rows = [self._row(record) for record in reader]
        parsed = [row for row in rows if row is not None]
        if not parsed:
            raise ValueError("Polar CSV contains no supported telemetry rows")
        return canonicalize_telemetry_rows(parsed)

    def _row(self, raw: dict[str | None, str | None]) -> dict[str, Any] | None:
        record = {
            normalized_key(str(key)): str(value or "")
            for key, value in raw.items()
            if key is not None
        }
        timestamp = first_value(record, ("timestamp", "datetime", "date_time", "time"))
        heart_rate = number(first_value(record, ("heart_rate", "hr", "bpm")))
        intervals = rr_values(first_value(record, ("rr_intervals", "rr_interval", "rr_ms", "rri", "rr")))
        if not timestamp or (heart_rate is None and not intervals):
            return None
        return {
            "timestamp": timestamp,
            "original_timestamp": timestamp,
            "heart_rate_bpm": heart_rate,
            "rr_interval": intervals[0] if intervals else None,
            "rr_intervals": intervals,
            "source": "polar_csv",
            "device_model": "Polar device (model required for HRV eligibility)",
            "quality_reason": "device_model_not_confirmed",
        }
