"""Apple Health export.xml importer for Apple Watch trend telemetry."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from xml.etree.ElementTree import iterparse

from core.telemetry.contract import (
    METHOD_PPG,
    QUALITY_UNKNOWN,
    SOURCE_WATCH_PPG,
    canonicalize_telemetry_rows,
)


_HEART_RATE = "HKQuantityTypeIdentifierHeartRate"
_OXYGEN = "HKQuantityTypeIdentifierOxygenSaturation"
_HRV_SDNN = "HKQuantityTypeIdentifierHeartRateVariabilitySDNN"


class AppleHealthXmlImporter:
    """Parse the standard Apple Health XML export without inferring RR intervals."""

    import_type = "apple_health_xml"
    parser_version = "apple-health-xml-v1"

    def import_data(self, path: str | Path) -> list[dict[str, Any]]:
        rows: dict[str, dict[str, Any]] = {}
        for _, element in iterparse(str(path), events=("end",)):
            if element.tag != "Record":
                continue
            record_type = element.attrib.get("type")
            timestamp = element.attrib.get("startDate")
            if record_type not in {_HEART_RATE, _OXYGEN, _HRV_SDNN} or not timestamp:
                element.clear()
                continue
            try:
                value = float(element.attrib.get("value", ""))
            except ValueError:
                element.clear()
                continue

            row = rows.setdefault(timestamp, self._base_row(timestamp, element.attrib))
            if record_type == _HEART_RATE:
                row["heart_rate_bpm"] = value
            elif record_type == _OXYGEN:
                row["spo2"] = value * 100 if value <= 1 else value
            else:
                row["device_reported_hrv_sdnn_ms"] = value
            element.clear()

        return canonicalize_telemetry_rows(list(rows.values()))

    @staticmethod
    def _base_row(timestamp: str, attributes: dict[str, str]) -> dict[str, Any]:
        return {
            "timestamp": timestamp,
            "original_timestamp": timestamp,
            "source": "apple_health_xml",
            "device_type": SOURCE_WATCH_PPG,
            "device_model": attributes.get("sourceName") or "Apple Health",
            "measurement_method": METHOD_PPG,
            "signal_quality": QUALITY_UNKNOWN,
            "quality_reason": "apple_health_export_has_no_raw_rr_intervals",
        }
