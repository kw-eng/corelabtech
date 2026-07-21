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

from services.csv_parser import parse_csv_file
from services.fit_parser import parse_fit_file


CSV_PARSER_VERSION = "csv-v1"
FIT_PARSER_VERSION = "fit-v3"

CSV_DEVICE = "Checkme O2"
FIT_DEVICE = "Garmin"


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


# =========================================================
# CSV IMPORT
# =========================================================

def import_csv_file(
    *,
    path: str | Path,
    filename: str,
    session_id: str,
    user_id: str | None = None,
) -> ImportResult:
    """Parse and persist a pulse oximeter CSV upload.

    The transaction creates import metadata first, writes validated telemetry
    rows, then marks the import as completed so duplicates can be detected.
    """

    path = normalize_path(path)
    session_id = required_text(session_id, "session_id")
    user_id = optional_text(user_id) or extract_user_id(session_id)

    validate_file(path)

    parsed_rows = parse_csv_file(path)
    valid_rows = validate_csv_rows(parsed_rows)

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

        import_id = create_csv_import(
            cursor,
            session_id=session_id,
            user_id=user_id,
            filename=filename,
            file_hash=file_hash,
            records_parsed=len(parsed_rows),
            device=CSV_DEVICE,
            parser_version=CSV_PARSER_VERSION,
        )

        records_saved = insert_csv_measurements(
            cursor,
            import_id=import_id,
            session_id=session_id,
            user_id=user_id,
            filename=filename,
            rows=valid_rows,
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
            parser_version=CSV_PARSER_VERSION,
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


# =========================================================
# FIT IMPORT
# =========================================================

def import_fit_file(
    *,
    path: str | Path,
    filename: str,
    session_id: str,
    user_id: str | None = None,
) -> ImportResult:
    """Parse and persist a Garmin FIT upload.

    FIT metadata is kept alongside measurements so the research pipeline can
    later trace a session back to the originating device/import.
    """

    path = normalize_path(path)
    session_id = required_text(session_id, "session_id")
    user_id = optional_text(user_id) or extract_user_id(session_id)

    validate_file(path)

    parsed_rows = parse_fit_file(path)
    valid_rows = validate_fit_rows(parsed_rows)

    file_hash = calculate_file_hash(path)
    file_size = path.stat().st_size

    metadata = extract_fit_metadata(valid_rows)

    connection = db()
    cursor = connection.cursor()

    try:
        duplicate = find_fit_import(
            cursor,
            session_id=session_id,
            file_hash=file_hash,
        )

        if duplicate:
            if duplicate.get("parser_version") == FIT_PARSER_VERSION:
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
                    status = 'processing',
                    error_message = NULL
                WHERE id = %s
                """,
                (
                    user_id,
                    filename,
                    file_size,
                    len(parsed_rows),
                    FIT_PARSER_VERSION,
                    metadata.get("manufacturer"),
                    metadata.get("product"),
                    metadata.get("device_serial"),
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
                parser_version=FIT_PARSER_VERSION,
                manufacturer=metadata.get("manufacturer"),
                product=metadata.get("product"),
                device_serial=metadata.get("device_serial"),
            )

        records_saved = insert_fit_measurements(
            cursor,
            import_id=import_id,
            session_id=session_id,
            user_id=user_id,
            filename=filename,
            rows=valid_rows,
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
            parser_version=FIT_PARSER_VERSION,
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

        pulse = first_not_none(
            row.get("pulse"),
            row.get("heart_rate"),
        )

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

        heart_rate = first_not_none(
            row.get("heart_rate"),
            row.get("pulse"),
            row.get("hr"),
        )

        hrv = row.get("hrv")
        rr_interval = row.get("rr_interval")
        spo2 = row.get("spo2")

        if timestamp is None:
            continue

        if all(
            value is None
            for value in (
                heart_rate,
                hrv,
                rr_interval,
                spo2,
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
