"""Canonical telemetry vocabulary shared by import and merge services.

The constants deliberately describe the measurement method, rather than making
clinical claims about an unknown device.  An uploaded FIT file is not proof that
the wearer used a chest strap; device-specific capability resolution belongs in
the future importer/catalog layer.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

SCHEMA_VERSION = "telemetry-v1"

METHOD_ECG = "ecg"
METHOD_PPG = "ppg"
METHOD_UNKNOWN = "unknown"

SOURCE_CHEST_HRM = "chest_hrm"
SOURCE_FINGER_OXIMETER = "finger_oximeter"
SOURCE_WEARABLE_FIT = "wearable_fit"
SOURCE_WATCH_PPG = "watch_ppg"
SOURCE_UNKNOWN = "unknown"

QUALITY_HIGH = "high"
QUALITY_MEDIUM = "medium"
QUALITY_UNKNOWN = "unknown"


@dataclass(frozen=True)
class TelemetrySample:
    """Canonical signal payload returned by every telemetry importer.

    Importer adapters determine whether a device field is heart rate or an
    auxiliary PPG pulse before creating this model.  The shared layer never
    guesses that meaning from a column alias.
    """

    timestamp: Any = None
    original_timestamp: str | None = None
    heart_rate_bpm: Any = None
    pulse_rate_bpm: Any = None
    rr_interval: Any = None
    rr_intervals: list[Any] | None = None
    spo2: Any = None
    respiration_rate: Any = None
    temperature: Any = None
    motion: Any = None
    source: str | None = None
    device_type: str | None = None
    device_model: str | None = None
    measurement_method: str | None = None
    signal_quality: str | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "TelemetrySample":
        """Read already-classified parser output into the canonical model."""

        packet = row.get("rr_intervals")
        rr_intervals = list(packet) if isinstance(packet, (list, tuple)) else []

        return cls(
            timestamp=row.get("timestamp"),
            original_timestamp=row.get("original_timestamp"),
            heart_rate_bpm=row.get("heart_rate_bpm"),
            pulse_rate_bpm=row.get("pulse_rate_bpm"),
            rr_interval=row.get("rr_interval"),
            rr_intervals=rr_intervals,
            spo2=row.get("spo2"),
            respiration_rate=row.get("respiration_rate"),
            temperature=row.get("temperature"),
            motion=row.get("motion"),
            source=row.get("source"),
            device_type=row.get("device_type"),
            device_model=row.get("device_model"),
            measurement_method=row.get("measurement_method"),
            signal_quality=row.get("signal_quality"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return the stable fields while preserving importer-specific extras."""

        return asdict(self)


def canonicalize_telemetry_rows(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Guarantee canonical sample fields for every importer result."""

    normalized_rows = []
    for row in rows:
        normalized = dict(row)
        normalized.update(TelemetrySample.from_row(row).to_dict())
        normalized_rows.append(normalized)

    return normalized_rows


def pulse_oximeter_metadata() -> dict[str, str]:
    """Return conservative provenance for supported pulse-oximeter CSV files."""

    return {
        "device_type": SOURCE_FINGER_OXIMETER,
        "measurement_method": METHOD_PPG,
        "signal_quality": QUALITY_MEDIUM,
        "quality_reason": "manufacturer_signal_quality_not_exported",
    }


def fit_wearable_metadata() -> dict[str, str]:
    """Return provenance for FIT telemetry without assuming an HRM chest strap."""

    return {
        "device_type": SOURCE_WEARABLE_FIT,
        "measurement_method": METHOD_UNKNOWN,
        "signal_quality": QUALITY_UNKNOWN,
        "quality_reason": "device_measurement_method_not_confirmed",
    }
