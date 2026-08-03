"""Health Connect JSON adapter for exported or bridged record collections."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.telemetry.contract import (
    METHOD_PPG,
    QUALITY_UNKNOWN,
    SOURCE_WATCH_PPG,
    canonicalize_telemetry_rows,
)


def record_timestamp(record: dict[str, Any]) -> str | None:
    return record.get("time") or record.get("startTime") or record.get("start_time")


def record_value(record: dict[str, Any]) -> Any:
    value = record.get("value")
    if isinstance(value, dict):
        return value.get("value") or value.get("inPercent")
    return value


class HealthConnectJsonImporter:
    """Read a documented JSON bridge format without inferring raw RR intervals."""

    import_type = "health_connect_json"
    parser_version = "health-connect-json-v1"

    def import_data(self, path: str | Path) -> list[dict[str, Any]]:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        records = payload.get("records", payload) if isinstance(payload, dict) else payload
        if not isinstance(records, list):
            raise ValueError("Health Connect export must contain a records array")
        rows: dict[str, dict[str, Any]] = {}
        for record in records:
            if not isinstance(record, dict):
                continue
            timestamp = record_timestamp(record)
            record_type = str(record.get("type") or record.get("recordType") or "").lower()
            if not timestamp:
                continue
            row = rows.setdefault(timestamp, self._base_row(timestamp, record))
            value = record_value(record)
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                continue
            if "heartratevariability" in record_type or "hrv" in record_type:
                row["device_reported_hrv_rmssd_ms"] = numeric
            elif "oxygen" in record_type or "spo2" in record_type:
                row["spo2"] = numeric * 100 if numeric <= 1 else numeric
            elif "heartrate" in record_type or record_type == "hr":
                row["heart_rate_bpm"] = numeric
        parsed = [row for row in rows.values() if any(row.get(key) is not None for key in ("heart_rate_bpm", "spo2", "device_reported_hrv_rmssd_ms"))]
        if not parsed:
            raise ValueError("Health Connect export contains no supported telemetry rows")
        return canonicalize_telemetry_rows(parsed)

    @staticmethod
    def _base_row(timestamp: str, record: dict[str, Any]) -> dict[str, Any]:
        return {
            "timestamp": timestamp,
            "original_timestamp": timestamp,
            "source": "health_connect_json",
            "device_type": SOURCE_WATCH_PPG,
            "device_model": record.get("origin") or record.get("source") or "Health Connect",
            "measurement_method": METHOD_PPG,
            "signal_quality": QUALITY_UNKNOWN,
            "quality_reason": "health_connect_export_has_no_raw_rr_intervals",
        }
