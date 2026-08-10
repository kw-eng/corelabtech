# services/fit_parser.py

from __future__ import annotations

from collections import deque
import math
from typing import Any

from core.telemetry.device_catalog import resolve_garmin_product


RR_MIN_SECONDS = 0.3
RR_MAX_SECONDS = 2.0
RR_MAX_DELTA_SECONDS = 0.15
RR_MAX_DELTA_RATIO = 0.20

DEFAULT_HRV_WINDOW_BEATS = 60
MIN_RR_SAMPLES_FOR_HRV = 10

TELEMETRY_SCHEMA_VERSION = "telemetry-row-v1"


# =========================================================
# SAFE VALUES
# =========================================================

def safe_float(value: Any) -> float | None:
    """Return a finite float or None."""

    if value is None or isinstance(value, bool):
        return None

    try:
        result = float(value)
    except (TypeError, ValueError):
        return None

    if math.isnan(result) or math.isinf(result):
        return None

    return result


def normalize_timestamp(value: Any) -> str | None:
    """Normalize timestamp to an ISO-compatible string."""

    if value is None:
        return None

    try:
        return value.isoformat()
    except AttributeError:
        normalized = str(value).strip()
        return normalized or None


# =========================================================
# RR NORMALIZATION
# =========================================================

def normalize_rr_seconds(value: Any) -> float | None:
    """Normalize an RR interval to seconds.

    FIT HRV values are normally expressed in seconds. Values greater
    than 10 are treated as milliseconds for compatibility with other
    telemetry exporters.
    """

    normalized = safe_float(value)

    if normalized is None:
        return None

    if normalized > 10:
        normalized /= 1000.0

    return normalized


def extract_rr_values(value: Any) -> list[float]:
    """Extract and normalize one or multiple RR intervals."""

    raw_values = (
        value
        if isinstance(value, (list, tuple))
        else [value]
    )

    result: list[float] = []

    for item in raw_values:
        normalized = normalize_rr_seconds(item)

        if normalized is not None:
            result.append(normalized)

    return result


def is_valid_rr_interval(value: float | None) -> bool:
    """Check whether an RR interval is technically plausible."""

    return (
        value is not None
        and RR_MIN_SECONDS <= value <= RR_MAX_SECONDS
    )


def is_rr_artifact(
    value: float | None,
    previous_value: float | None,
) -> bool:
    """Detect an RR artifact using range and beat-to-beat deviation."""

    if not is_valid_rr_interval(value):
        return True

    if previous_value is None:
        return False

    delta = abs(value - previous_value)

    ratio = (
        delta / previous_value
        if previous_value
        else 0.0
    )

    return (
        delta > RR_MAX_DELTA_SECONDS
        or ratio > RR_MAX_DELTA_RATIO
    )


def append_filtered_rr(
    rr_window: deque[float],
    value: float | None,
    previous_value: float | None,
) -> tuple[float | None, bool]:
    """Append a valid RR value and report whether it was rejected."""

    if is_rr_artifact(value, previous_value):
        return previous_value, True

    if value is None:
        return previous_value, True

    rr_window.append(value)

    return value, False


# =========================================================
# HRV CALCULATION
# =========================================================

def calculate_rmssd_raw(values: list[float]) -> float | None:
    """Calculate RMSSD in the same unit as the supplied RR values."""

    if len(values) < 2:
        return None

    squared_differences = [
        (current - previous) ** 2
        for previous, current in zip(
            values,
            values[1:],
        )
    ]

    if not squared_differences:
        return None

    return math.sqrt(
        sum(squared_differences)
        / len(squared_differences)
    )


def calculate_rmssd(values: list[float]) -> float | None:
    """Calculate RMSSD in the source RR unit."""

    clean_values = [
        value
        for value in values
        if value is not None
    ]

    result = calculate_rmssd_raw(clean_values)

    if result is None:
        return None

    return round(result, 4)


def calculate_rmssd_ms(values: list[float]) -> float | None:
    """Calculate RMSSD and return the result in milliseconds."""

    clean_values = [
        value
        for value in values
        if value is not None
    ]

    result = calculate_rmssd_raw(clean_values)

    if result is None:
        return None

    # RR values below 10 are treated as seconds.
    if clean_values and max(clean_values) < 10:
        result *= 1000.0

    return round(result, 2)


def calculate_hrv(rr_intervals: list[float]) -> float | None:
    """Backward-compatible HRV helper returning rolling RMSSD in ms."""

    return calculate_rmssd_ms(rr_intervals)


# =========================================================
# FIT HRV PACKETS
# =========================================================

def extract_hrv_packets(fitfile: Any) -> list[list[float]]:
    """Extract RR packets from FIT HRV messages."""

    packets: list[list[float]] = []

    try:
        for message in fitfile.get_messages("hrv"):
            rr_values: list[float] = []

            for field in message:
                field_name = str(field.name).lower()

                if field_name in {
                    "time",
                    "rr_interval",
                    "rr",
                    "rr_intervals",
                }:
                    rr_values.extend(
                        extract_rr_values(field.value)
                    )

            if rr_values:
                packets.append(rr_values)

    except Exception as exc:
        print("FIT HRV PARSE ERROR:", exc)

    return packets


def apply_hrv_packets(
    rows: list[dict[str, Any]],
    hrv_packets: list[list[float]],
) -> None:
    """Attach FIT HRV packets to normalized record rows.

    FIT record and HRV message counts are not guaranteed to be equal.
    This implementation retains the current index-based association,
    while preserving all RR values from each available packet.
    """

    if not rows or not hrv_packets:
        return

    for index, row in enumerate(rows):
        packet = (
            hrv_packets[index]
            if index < len(hrv_packets)
            else []
        )

        if not packet:
            continue

        existing_rr = row.get("rr_intervals") or []

        merged_rr = [
            *existing_rr,
            *packet,
        ]

        row["rr_intervals"] = merged_rr

        if row.get("rr_interval") is None:
            row["rr_interval"] = packet[0]


# =========================================================
# ROLLING HRV (RMSSD)
# =========================================================

def apply_rolling_hrv(
    rows: list[dict[str, Any]],
    *,
    window_size: int = DEFAULT_HRV_WINDOW_BEATS,
    minimum_samples: int = MIN_RR_SAMPLES_FOR_HRV,
) -> None:
    """Calculate rolling RMSSD from RR intervals.

    ``window_size`` represents the number of retained RR intervals,
    not a fixed number of seconds.

    The calculated HRV is stored in milliseconds in ``row["hrv"]``.
    """

    if not rows:
        return

    normalized_window_size = max(
        int(window_size),
        2,
    )

    normalized_minimum_samples = max(
        min(
            int(minimum_samples),
            normalized_window_size,
        ),
        2,
    )

    rr_window: deque[float] = deque(
        maxlen=normalized_window_size
    )

    previous_rr: float | None = None
    total_artifact_count = 0

    for row in rows:
        packet = extract_rr_values(
            row.get("rr_intervals") or []
        )

        if (
            not packet
            and row.get("rr_interval") is not None
        ):
            packet = extract_rr_values(
                row.get("rr_interval")
            )

        row_artifact_count = 0
        row_valid_rr_count = 0

        for rr_value in packet:
            previous_rr, is_artifact = append_filtered_rr(
                rr_window,
                rr_value,
                previous_rr,
            )

            if is_artifact:
                row_artifact_count += 1
                total_artifact_count += 1
            else:
                row_valid_rr_count += 1

        row["rr_count_window"] = len(rr_window)
        row["rr_valid_count"] = row_valid_rr_count
        row["rr_artifact_count"] = row_artifact_count
        row["rr_artifact_count_total"] = total_artifact_count

        if len(rr_window) >= normalized_minimum_samples:
            row["hrv"] = calculate_rmssd_ms(
                list(rr_window)
            )
            row["hrv_metric"] = (
                f"rmssd_rolling_{normalized_window_size}_beats"
            )
        else:
            row["hrv"] = None
            row["hrv_metric"] = None


# =========================================================
# TECHNICAL DEVICE METADATA
# =========================================================

def extract_external_hrm_metadata(
    fitfile: Any,
) -> dict[str, Any]:
    """Extract external HR sensor metadata for diagnostics.

    Device metadata must not determine whether HRV or another analysis
    is available. Analysis availability depends on actual signals.
    """

    try:
        for message in fitfile.get_messages("device_info"):
            fields = {
                str(field.name).lower(): field.value
                for field in message
            }

            if fields.get("device_index") == "creator":
                continue

            model = resolve_garmin_product(
                fields.get("garmin_product")
            )

            if not model:
                continue

            return {
                "manufacturer": (
                    fields.get("manufacturer")
                    or "garmin"
                ),
                "product": model,
                "device_model": model,
                "device_serial": fields.get(
                    "serial_number"
                ),
            }

    except Exception as exc:
        print("FIT DEVICE INFO PARSE ERROR:", exc)

    return {}


def apply_device_metadata(
    rows: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> None:
    """Attach technical source metadata to normalized rows."""

    if not metadata:
        return

    filtered_metadata = {
        key: value
        for key, value in metadata.items()
        if value is not None
    }

    for row in rows:
        row.update(filtered_metadata)


# =========================================================
# RECORD HELPERS
# =========================================================

def create_empty_record() -> dict[str, Any]:
    """Create a normalized telemetry row."""

    return {
        "timestamp": None,
        "original_timestamp": None,

        "heart_rate": None,
        "heart_rate_bpm": None,

        "pulse": None,
        "pulse_rate_bpm": None,

        "spo2": None,

        "rr_interval": None,
        "rr_intervals": [],

        "hrv": None,
        "hrv_metric": None,

        "rr_count_window": 0,
        "rr_valid_count": 0,
        "rr_artifact_count": 0,
        "rr_artifact_count_total": 0,

        "source": "fit",
        "source_type": "wearable_telemetry",
        "telemetry_schema_version": (
            TELEMETRY_SCHEMA_VERSION
        ),
    }


def apply_record_field(
    row: dict[str, Any],
    field_name: str,
    value: Any,
) -> None:
    """Map one FIT record field to the normalized telemetry schema."""

    normalized_name = str(field_name).lower()

    if normalized_name == "timestamp":
        normalized_timestamp = normalize_timestamp(value)

        row["timestamp"] = normalized_timestamp
        row["original_timestamp"] = normalized_timestamp
        return

    if normalized_name in {
        "heart_rate",
        "hr",
    }:
        heart_rate = safe_float(value)

        row["heart_rate"] = heart_rate
        row["heart_rate_bpm"] = heart_rate
        return

    if normalized_name in {
        "pulse",
        "pulse_rate",
        "pulse_rate_bpm",
    }:
        pulse = safe_float(value)

        row["pulse"] = pulse
        row["pulse_rate_bpm"] = pulse
        return

    if normalized_name in {
        "spo2",
        "oxygen_saturation",
    }:
        row["spo2"] = safe_float(value)
        return

    if normalized_name in {
        "rr_interval",
        "rr",
        "rr_intervals",
    }:
        rr_values = extract_rr_values(value)

        if rr_values:
            row["rr_intervals"] = rr_values
            row["rr_interval"] = rr_values[0]


def should_store_record(
    row: dict[str, Any],
) -> bool:
    """Return True when the normalized row contains usable data."""

    return any([
        row.get("timestamp") is not None,
        row.get("heart_rate") is not None,
        row.get("pulse") is not None,
        row.get("spo2") is not None,
        row.get("rr_interval") is not None,
        bool(row.get("rr_intervals")),
    ])


def clean_non_finite_values(
    rows: list[dict[str, Any]],
) -> None:
    """Replace NaN and infinity values with None."""

    for row in rows:
        for key, value in list(row.items()):
            if (
                isinstance(value, float)
                and (
                    math.isnan(value)
                    or math.isinf(value)
                )
            ):
                row[key] = None


# =========================================================
# FIT PARSER
# =========================================================

def parse_fit_file(
    file_path: Any,
) -> list[dict[str, Any]]:
    """Parse a FIT file into normalized telemetry records.

    The parser returns normalized rows only. Telemetry capability
    scanning and quality assessment should be executed by the import
    or preflight service after this function returns.
    """

    try:
        from fitparse import FitFile
    except ImportError as exc:
        raise RuntimeError(
            "FIT parser dependency is missing: install fitparse"
        ) from exc

    try:
        fitfile = FitFile(str(file_path))
    except Exception as exc:
        print("FIT OPEN ERROR:", exc)
        raise

    rows: list[dict[str, Any]] = []

    try:
        hrv_packets = extract_hrv_packets(fitfile)

        external_hrm_metadata = (
            extract_external_hrm_metadata(fitfile)
        )

        for record in fitfile.get_messages("record"):
            row = create_empty_record()

            try:
                for field in record:
                    apply_record_field(
                        row,
                        str(field.name),
                        field.value,
                    )

                if should_store_record(row):
                    rows.append(row)

            except Exception as exc:
                print("FIT RECORD ERROR:", exc)
                continue

    except Exception as exc:
        print("FIT PARSE ERROR:", exc)
        return []

    if not rows:
        return []

    # Attach raw RR packets from FIT HRV messages.
    apply_hrv_packets(
        rows,
        hrv_packets,
    )

    # Calculate rolling RMSSD in milliseconds.
    apply_rolling_hrv(
        rows,
        window_size=DEFAULT_HRV_WINDOW_BEATS,
        minimum_samples=MIN_RR_SAMPLES_FOR_HRV,
    )

    # Preserve source metadata for technical diagnostics only.
    apply_device_metadata(
        rows,
        external_hrm_metadata,
    )

    clean_non_finite_values(rows)

    return rows