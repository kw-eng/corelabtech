"""Validated FIT/CSV ingestion pipeline.

The route layer saves uploads to a temporary file, then calls this module to
parse, validate, deduplicate and persist telemetry into PostgreSQL.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from database_postgres import db
from core.telemetry.contract import (
    SCHEMA_VERSION,
    pulse_oximeter_metadata,
)
from services.hrv_pipeline import annotate_hrv_rmssd_timeline
from core.telemetry.device_catalog import resolve_device_capability, resolve_fit_device
from services.importers.registry import get_importer
from services.telemetry_time import normalize_rows_timestamps

from repositories.data_repository import (
    complete_csv_import,
    complete_fit_import,
    create_csv_import,
    create_fit_import,
    ensure_research_user,
    find_csv_import,
    find_fit_import,
    insert_csv_measurements,
    insert_fit_measurements,
)

TIMESTAMP_NORMALIZATION_VERSION = "time-v1"

CSV_DEVICE = "Checkme O2"
FIT_DEVICE = "FIT-compatible wearable"


# =========================================================
# EXCEPTIONS
# =========================================================

class DataIngestionError(Exception):
    """Base error returned to API routes as a controlled ingestion failure."""

    pass


class DuplicateImportError(DataIngestionError):
    """Raised when the same file hash has already been imported for a session."""

    def __init__(
        self,
        *,
        import_type: str,
        import_id: int,
        records_saved: int,
    ):
        self.import_type = import_type
        self.import_id = import_id
        self.records_saved = records_saved

        super().__init__(
            f"{import_type.upper()} file has already been "
            "imported for this session"
        )


class EmptyImportError(DataIngestionError):
    """Raised when a parser returns no rows at all."""

    pass


class InvalidImportDataError(DataIngestionError):
    """Raised when parsed rows exist but none pass measurement validation."""

    pass


# =========================================================
# RESULT
# =========================================================

@dataclass(frozen=True)
class ImportResult:
    """Summary of one completed file import."""

    import_id: int
    import_type: str

    session_id: str
    user_id: str

    filename: str
    file_hash: str

    records_parsed: int
    records_saved: int
    records_rejected: int

    first_timestamp: str | None
    last_timestamp: str | None

    device: str
    parser_version: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def preview_telemetry_file(
    *,
    path: str | Path,
    import_type: str,
    source_timezone: str | None = None,
    device_model: str | None = None,
) -> dict[str, Any]:
    """Parse an upload without persistence and return bounded import facts."""

    path = normalize_path(path)
    validate_file(path)
    importer = get_importer(import_type)
    parsed_rows = importer.import_data(path)
    validator = validate_csv_rows if import_type == "csv" else validate_fit_rows
    valid_rows = normalize_rows_timestamps(
        validator(parsed_rows), source_timezone=source_timezone
    )

    inferred_model = next(
        (row.get("device_model") for row in valid_rows if row.get("device_model")),
        None,
    )
    resolved_model = device_model or inferred_model
    if import_type == "csv":
        capability = pulse_oximeter_metadata()
    elif import_type == "fit":
        capability = resolve_fit_device(resolved_model)
    else:
        capability = resolve_device_capability(resolved_model)

    has_rr = any(row.get("rr_intervals") or row.get("rr_interval") for row in valid_rows)
    reported_hrv = any(
        row.get("device_reported_hrv_sdnn_ms") is not None
        or row.get("device_reported_hrv_rmssd_ms") is not None
        for row in valid_rows
    )
    signals = {
        "heart_rate": any(row.get("heart_rate_bpm") is not None for row in valid_rows),
        "pulse": any(row.get("pulse_rate_bpm") is not None for row in valid_rows),
        "spo2": any(row.get("spo2") is not None for row in valid_rows),
        "raw_rr": has_rr,
        "reported_hrv": reported_hrv,
    }
    if has_rr and capability.get("measurement_method") == "ecg":
        hrv_status = "eligible_from_raw_rr"
    elif has_rr:
        hrv_status = "raw_rr_requires_source_review"
    elif reported_hrv:
        hrv_status = "reported_by_device_only"
    else:
        hrv_status = "not_available"

    first_timestamp, last_timestamp = get_timestamp_range(valid_rows)
    return {
        "status": "ready",
        "import_type": import_type,
        "parser_version": importer.parser_version,
        "records_parsed": len(parsed_rows),
        "records_valid": len(valid_rows),
        "records_rejected": len(parsed_rows) - len(valid_rows),
        "first_timestamp": first_timestamp,
        "last_timestamp": last_timestamp,
        "device_model": resolved_model or "unknown",
        "device_type": capability.get("device_type", "unknown"),
        "measurement_method": capability.get("measurement_method", "unknown"),
        "signal_quality": capability.get("signal_quality", "unknown"),
        "signals": signals,
        "hrv_status": hrv_status,
    }


# =========================================================
# CSV IMPORT
# =========================================================

def import_csv_file(
    *,
    path: str | Path,
    filename: str,
    session_id: str,
    user_id: str | None = None,
    source_timezone: str | None = None,
) -> ImportResult:
    """Parse and persist a pulse oximeter CSV upload.

    The transaction creates import metadata first, writes validated telemetry
    rows, then marks the import as completed so duplicates can be detected.
    """

    path = normalize_path(path)
    session_id = required_text(session_id, "session_id")
    user_id = optional_text(user_id) or extract_user_id(session_id)

    validate_file(path)

    importer = get_importer("csv")
    parsed_rows = importer.import_data(path)
    valid_rows = normalize_rows_timestamps(
        validate_csv_rows(parsed_rows),
        source_timezone=source_timezone,
    )

    file_hash = calculate_file_hash(path)

    connection = db()
    cursor = connection.cursor()

    try:
        duplicate = find_csv_import(
            cursor,
            session_id=session_id,
            file_hash=file_hash,
        )

        if duplicate:
            raise DuplicateImportError(
                import_type="csv",
                import_id=duplicate["id"],
                records_saved=duplicate["records_saved"] or 0,
            )

        ensure_research_user(
            cursor,
            user_id=user_id,
            notes="Auto-created during CSV import",
        )

        telemetry_metadata = pulse_oximeter_metadata()

        import_id = create_csv_import(
            cursor,
            session_id=session_id,
            user_id=user_id,
            filename=filename,
            file_hash=file_hash,
            records_parsed=len(parsed_rows),
            device=CSV_DEVICE,
            parser_version=importer.parser_version,
            device_type=telemetry_metadata["device_type"],
            device_model="checkme_o2",
            measurement_method=telemetry_metadata["measurement_method"],
            telemetry_schema_version=SCHEMA_VERSION,
            source_timezone=valid_rows[0]["source_timezone"],
            timestamp_normalization_version=TIMESTAMP_NORMALIZATION_VERSION,
        )

        records_saved = insert_csv_measurements(
            cursor,
            import_id=import_id,
            session_id=session_id,
            user_id=user_id,
            filename=filename,
            rows=valid_rows,
            telemetry_metadata=telemetry_metadata,
        )

        records_rejected = len(parsed_rows) - records_saved

        first_timestamp, last_timestamp = get_timestamp_range(
            valid_rows
        )

        complete_csv_import(
            cursor,
            import_id=import_id,
            records_saved=records_saved,
            records_rejected=records_rejected,
            first_timestamp=first_timestamp,
            last_timestamp=last_timestamp,
        )

        connection.commit()

        return ImportResult(
            import_id=import_id,
            import_type="csv",
            session_id=session_id,
            user_id=user_id,
            filename=filename,
            file_hash=file_hash,
            records_parsed=len(parsed_rows),
            records_saved=records_saved,
            records_rejected=records_rejected,
            first_timestamp=first_timestamp,
            last_timestamp=last_timestamp,
            device=CSV_DEVICE,
            parser_version=importer.parser_version,
        )

    except DuplicateImportError:
        connection.rollback()
        raise

    except Exception as exc:
        connection.rollback()

        raise DataIngestionError(
            f"CSV import failed: {exc}"
        ) from exc

    finally:
        cursor.close()
        connection.close()


def import_external_telemetry_file(
    *,
    path: str | Path,
    filename: str,
    session_id: str,
    import_type: str,
    user_id: str | None = None,
    source_timezone: str | None = None,
    device_model: str | None = None,
) -> ImportResult:
    """Persist non-FIT HR/HRV adapters through the traceable wearable pipeline."""

    path = normalize_path(path)
    session_id = required_text(session_id, "session_id")
    user_id = optional_text(user_id) or extract_user_id(session_id)
    validate_file(path)

    importer = get_importer(import_type)
    parsed_rows = importer.import_data(path)
    valid_rows = normalize_rows_timestamps(
        validate_fit_rows(parsed_rows), source_timezone=source_timezone
    )
    file_hash = calculate_file_hash(path)
    file_size = path.stat().st_size
    inferred_model = next(
        (row.get("device_model") for row in valid_rows if row.get("device_model")),
        None,
    )
    resolved_model = device_model or inferred_model or import_type
    capability = resolve_device_capability(resolved_model)
    for row in valid_rows:
        row["device_type"] = capability["device_type"]
        row["device_model"] = resolved_model
        row["measurement_method"] = capability["measurement_method"]
        row["signal_quality"] = capability["signal_quality"]
        row["quality_reason"] = capability["quality_reason"]
    annotate_hrv_rmssd_timeline(valid_rows)

    connection = db()
    cursor = connection.cursor()
    try:
        duplicate = find_fit_import(cursor, session_id=session_id, file_hash=file_hash)
        if duplicate:
            raise DuplicateImportError(
                import_type=import_type,
                import_id=duplicate["id"],
                records_saved=duplicate["records_saved"] or 0,
            )
        ensure_research_user(cursor, user_id=user_id, notes=f"Auto-created during {import_type} import")
        import_id = create_fit_import(
            cursor,
            session_id=session_id,
            user_id=user_id,
            filename=filename,
            file_hash=file_hash,
            file_size=file_size,
            records_parsed=len(parsed_rows),
            parser_version=importer.parser_version,
            manufacturer=import_type,
            product=resolved_model,
            device_type=capability["device_type"],
            device_model=resolved_model,
            measurement_method=capability["measurement_method"],
            telemetry_schema_version=SCHEMA_VERSION,
            source_timezone=valid_rows[0]["source_timezone"],
            timestamp_normalization_version=TIMESTAMP_NORMALIZATION_VERSION,
            import_type=import_type,
        )
        records_saved = insert_fit_measurements(
            cursor,
            import_id=import_id,
            session_id=session_id,
            user_id=user_id,
            filename=filename,
            rows=valid_rows,
            telemetry_metadata=capability,
        )
        first_timestamp, last_timestamp = get_timestamp_range(valid_rows)
        complete_fit_import(
            cursor,
            import_id=import_id,
            records_saved=records_saved,
            records_rejected=len(parsed_rows) - records_saved,
            first_timestamp=first_timestamp,
            last_timestamp=last_timestamp,
        )
        connection.commit()
        return ImportResult(
            import_id=import_id,
            import_type=import_type,
            session_id=session_id,
            user_id=user_id,
            filename=filename,
            file_hash=file_hash,
            records_parsed=len(parsed_rows),
            records_saved=records_saved,
            records_rejected=len(parsed_rows) - records_saved,
            first_timestamp=first_timestamp,
            last_timestamp=last_timestamp,
            device=resolved_model,
            parser_version=importer.parser_version,
        )
    except DuplicateImportError:
        connection.rollback()
        raise
    except Exception as exc:
        connection.rollback()
        raise DataIngestionError(f"{import_type} import failed: {exc}") from exc
    finally:
        cursor.close()
        connection.close()


# =========================================================
# FIT IMPORT
# =========================================================

def import_fit_file(
    *,
    path: str | Path,
    filename: str,
    session_id: str,
    user_id: str | None = None,
    source_timezone: str | None = "UTC",
    device_model: str | None = None,
) -> ImportResult:
    """Parse and persist a FIT upload from a compatible wearable.

    FIT metadata is kept alongside measurements so the research pipeline can
    later trace a session back to the originating device/import.
    """

    path = normalize_path(path)
    session_id = required_text(session_id, "session_id")
    user_id = optional_text(user_id) or extract_user_id(session_id)

    validate_file(path)

    importer = get_importer("fit")
    parsed_rows = importer.import_data(path)
    valid_rows = normalize_rows_timestamps(
        validate_fit_rows(parsed_rows),
        source_timezone=source_timezone,
    )

    file_hash = calculate_file_hash(path)
    file_size = path.stat().st_size

    metadata = extract_fit_metadata(valid_rows)
    resolved_model = device_model or metadata.get("product")
    telemetry_metadata = resolve_fit_device(resolved_model)
    for row in valid_rows:
        row["device_type"] = telemetry_metadata["device_type"]
        row["device_model"] = resolved_model
        row["measurement_method"] = telemetry_metadata["measurement_method"]
        row["signal_quality"] = telemetry_metadata["signal_quality"]
    annotate_hrv_rmssd_timeline(valid_rows)

    connection = db()
    cursor = connection.cursor()

    try:
        duplicate = find_fit_import(
            cursor,
            session_id=session_id,
            file_hash=file_hash,
        )

        if duplicate:
            if duplicate.get("parser_version") == importer.parser_version:
                raise DuplicateImportError(
                    import_type="fit",
                    import_id=duplicate["id"],
                    records_saved=duplicate["records_saved"] or 0,
                )

            import_id = duplicate["id"]

            cursor.execute(
                """
                DELETE FROM fit_data
                WHERE import_id = %s
                """,
                (import_id,),
            )

            cursor.execute(
                """
                UPDATE fit_imports
                SET
                    user_id = %s,
                    filename = %s,
                    file_size = %s,
                    records_parsed = %s,
                    records_saved = 0,
                    records_rejected = 0,
                    parser_version = %s,
                    manufacturer = %s,
                    product = %s,
                    device_serial = %s,
                    device_type = %s,
                    device_model = %s,
                    measurement_method = %s,
                    telemetry_schema_version = %s,
                    source_timezone = %s,
                    timestamp_normalization_version = %s,
                    status = 'processing',
                    error_message = NULL
                WHERE id = %s
                """,
                (
                    user_id,
                    filename,
                    file_size,
                    len(parsed_rows),
                    importer.parser_version,
                    metadata.get("manufacturer"),
                    metadata.get("product"),
                    metadata.get("device_serial"),
                    telemetry_metadata["device_type"],
                    resolved_model,
                    telemetry_metadata["measurement_method"],
                    SCHEMA_VERSION,
                    valid_rows[0]["source_timezone"],
                    TIMESTAMP_NORMALIZATION_VERSION,
                    import_id,
                ),
            )

        else:
            ensure_research_user(
                cursor,
                user_id=user_id,
                notes="Auto-created during FIT import",
            )

            import_id = create_fit_import(
                cursor,
                session_id=session_id,
                user_id=user_id,
                filename=filename,
                file_hash=file_hash,
                file_size=file_size,
                records_parsed=len(parsed_rows),
                parser_version=importer.parser_version,
                manufacturer=metadata.get("manufacturer"),
                product=metadata.get("product"),
                device_serial=metadata.get("device_serial"),
                device_type=telemetry_metadata["device_type"],
                device_model=resolved_model,
                measurement_method=telemetry_metadata["measurement_method"],
                telemetry_schema_version=SCHEMA_VERSION,
                source_timezone=valid_rows[0]["source_timezone"],
                timestamp_normalization_version=TIMESTAMP_NORMALIZATION_VERSION,
            )

        records_saved = insert_fit_measurements(
            cursor,
            import_id=import_id,
            session_id=session_id,
            user_id=user_id,
            filename=filename,
            rows=valid_rows,
            telemetry_metadata=telemetry_metadata,
        )

        records_rejected = len(parsed_rows) - records_saved

        first_timestamp, last_timestamp = get_timestamp_range(
            valid_rows
        )

        complete_fit_import(
            cursor,
            import_id=import_id,
            records_saved=records_saved,
            records_rejected=records_rejected,
            first_timestamp=first_timestamp,
            last_timestamp=last_timestamp,
        )

        connection.commit()

        return ImportResult(
            import_id=import_id,
            import_type="fit",
            session_id=session_id,
            user_id=user_id,
            filename=filename,
            file_hash=file_hash,
            records_parsed=len(parsed_rows),
            records_saved=records_saved,
            records_rejected=records_rejected,
            first_timestamp=first_timestamp,
            last_timestamp=last_timestamp,
            device=FIT_DEVICE,
            parser_version=importer.parser_version,
        )

    except DuplicateImportError:
        connection.rollback()
        raise

    except Exception as exc:
        connection.rollback()

        raise DataIngestionError(
            f"FIT import failed: {exc}"
        ) from exc

    finally:
        cursor.close()
        connection.close()


# =========================================================
# CSV VALIDATION
# =========================================================

def validate_csv_rows(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep only CSV rows with a timestamp and plausible SpO2 or pulse."""

    if not rows:
        raise EmptyImportError(
            "CSV parser returned no records"
        )

    valid_rows = []

    for row in rows:
        timestamp = row.get("timestamp")
        spo2 = row.get("spo2")

        pulse = row.get("pulse_rate_bpm")

        if timestamp is None:
            continue

        if spo2 is None and pulse is None:
            continue

        if spo2 is not None:
            try:
                if not 50 <= float(spo2) <= 100:
                    continue
            except (TypeError, ValueError):
                continue

        if pulse is not None:
            try:
                if not 20 <= float(pulse) <= 250:
                    continue
            except (TypeError, ValueError):
                continue

        valid_rows.append(row)

    if not valid_rows:
        raise InvalidImportDataError(
            "CSV contains no valid timestamp, "
            "SpO2 or pulse measurements"
        )

    return valid_rows


# =========================================================
# FIT VALIDATION
# =========================================================

def validate_fit_rows(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep only FIT rows with a timestamp and at least one useful signal."""

    if not rows:
        raise EmptyImportError(
            "FIT parser returned no records"
        )

    valid_rows = []

    for row in rows:
        timestamp = row.get("timestamp")

        heart_rate = row.get("heart_rate_bpm")

        hrv = row.get("hrv")
        rr_interval = row.get("rr_interval")
        rr_intervals = row.get("rr_intervals") or []
        spo2 = row.get("spo2")
        device_reported_hrv = (
            row.get("device_reported_hrv_sdnn_ms")
            or row.get("device_reported_hrv_rmssd_ms")
        )

        if timestamp is None:
            continue

        if all(
            value is None
            for value in (
                heart_rate,
                hrv,
                rr_interval,
                rr_intervals,
                spo2,
                device_reported_hrv,
            )
        ):
            continue

        if heart_rate is not None:
            try:
                if not 20 <= float(heart_rate) <= 250:
                    continue
            except (TypeError, ValueError):
                continue

        valid_rows.append(row)

    if not valid_rows:
        raise InvalidImportDataError(
            "FIT contains no valid measurements"
        )

    return valid_rows


# =========================================================
# FILE HELPERS
# =========================================================

def calculate_file_hash(
    path: str | Path,
) -> str:
    """Return a SHA-256 hash used to prevent duplicate imports."""

    digest = hashlib.sha256()

    with open(path, "rb") as source:
        for chunk in iter(
            lambda: source.read(8192),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def validate_file(path: Path) -> None:
    """Reject missing, non-file or empty upload paths before parsing."""

    if not path.exists():
        raise FileNotFoundError(
            f"File does not exist: {path}"
        )

    if not path.is_file():
        raise ValueError(
            f"Path is not a file: {path}"
        )

    if path.stat().st_size <= 0:
        raise ValueError(
            "Uploaded file is empty"
        )


def normalize_path(
    path: str | Path,
) -> Path:
    """Normalize user-supplied or route-supplied paths to absolute Path values."""

    return Path(path).expanduser().resolve()


# =========================================================
# IDENTIFIERS
# =========================================================

def extract_user_id(session_id: str) -> str:
    """Infer a subject id from generated session ids."""

    if "_S" in session_id:
        return session_id.rsplit("_S", 1)[0]

    return session_id


def required_text(
    value: Any,
    field_name: str,
) -> str:
    """Return stripped text or raise when a required field is empty."""

    normalized = (
        str(value).strip()
        if value is not None
        else ""
    )

    if not normalized:
        raise ValueError(
            f"{field_name} is required"
        )

    return normalized


def optional_text(
    value: Any,
) -> str | None:
    """Return stripped text, using None for blank optional fields."""

    if value is None:
        return None

    normalized = str(value).strip()

    return normalized or None


# =========================================================
# TIMESTAMPS / METADATA
# =========================================================

def get_timestamp_range(
    rows: list[dict[str, Any]],
) -> tuple[str | None, str | None]:
    """Calculate the first and last timestamps from validated rows."""

    timestamps = [
        str(row["timestamp"])
        for row in rows
        if row.get("timestamp") is not None
    ]

    if not timestamps:
        return None, None

    return min(timestamps), max(timestamps)


def extract_fit_metadata(
    rows: list[dict[str, Any]],
) -> dict[str, str | None]:
    """Pull device metadata from parsed FIT rows when available."""

    if not rows:
        return {
            "manufacturer": None,
            "product": None,
            "device_serial": None,
        }

    first = rows[0]

    return {
        "manufacturer": first.get("manufacturer"),
        "product": (
            first.get("product")
            or first.get("device")
        ),
        "device_serial": (
            first.get("device_serial")
            or first.get("serial_number")
        ),
    }


def first_not_none(*values):
    """Return the first non-None value from a list of signal aliases."""

    for value in values:
        if value is not None:
            return value

    return None
