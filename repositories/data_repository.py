"""Low-level SQL helpers for users, imports and raw telemetry rows.

Repository functions receive an existing cursor and intentionally do not commit;
service modules own transaction boundaries and rollback behavior.
"""

from __future__ import annotations

import json
from typing import Any

from psycopg2.extras import execute_values


# =========================================================
# USERS
# =========================================================

def ensure_research_user(
    cursor,
    *,
    user_id: str,
    notes: str,
) -> None:
    """
    Ensures that a research subject exists.

    This function does not commit the transaction.
    The caller owns commit/rollback.
    """

    cursor.execute(
        """
        INSERT INTO users (
            user_id,
            subject_id,
            role,
            is_active,
            notes
        )
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (user_id) DO NOTHING
        """,
        (
            user_id,
            user_id,
            "operator",
            True,
            notes,
        ),
    )


# =========================================================
# CSV IMPORT METADATA
# =========================================================

def find_csv_import(
    cursor,
    *,
    session_id: str,
    file_hash: str,
) -> dict[str, Any] | None:
    """Find an existing CSV import by session and file hash."""

    cursor.execute(
        """
        SELECT
            id,
            session_id,
            user_id,
            filename,
            file_hash,
            records_parsed,
            records_saved,
            records_rejected,
            status,
            error_message,
            first_timestamp,
            last_timestamp,
            imported_at
        FROM csv_imports
        WHERE session_id = %s
          AND file_hash = %s
        LIMIT 1
        """,
        (
            session_id,
            file_hash,
        ),
    )

    row = cursor.fetchone()

    if not row:
        return None

    return {
        "id": row[0],
        "session_id": row[1],
        "user_id": row[2],
        "filename": row[3],
        "file_hash": row[4],
        "records_parsed": row[5],
        "records_saved": row[6],
        "records_rejected": row[7],
        "status": row[8],
        "error_message": row[9],
        "first_timestamp": row[10],
        "last_timestamp": row[11],
        "imported_at": row[12],
    }


def create_csv_import(
    cursor,
    *,
    session_id: str,
    user_id: str,
    filename: str,
    file_hash: str,
    records_parsed: int,
    device: str,
    parser_version: str,
    device_type: str | None = None,
    device_model: str | None = None,
    measurement_method: str | None = None,
    telemetry_schema_version: str | None = None,
    source_timezone: str | None = None,
    timestamp_normalization_version: str | None = None,
) -> int:
    """Create a CSV import metadata row in processing state."""

    cursor.execute(
        """
        INSERT INTO csv_imports (
            session_id,
            user_id,
            filename,
            file_hash,
            records_parsed,
            records_saved,
            records_rejected,
            device,
            parser_version,
            device_type,
            device_model,
            measurement_method,
            telemetry_schema_version,
            source_timezone,
            timestamp_normalization_version,
            status
        )
        VALUES (
            %s, %s, %s, %s, %s,
            0, 0, %s, %s, %s, %s, %s, %s, %s, %s, 'processing'
        )
        RETURNING id
        """,
        (
            session_id,
            user_id,
            filename,
            file_hash,
            records_parsed,
            device,
            parser_version,
            device_type,
            device_model,
            measurement_method,
            telemetry_schema_version,
            source_timezone,
            timestamp_normalization_version,
        ),
    )

    return cursor.fetchone()[0]


def complete_csv_import(
    cursor,
    *,
    import_id: int,
    records_saved: int,
    records_rejected: int,
    first_timestamp: Any,
    last_timestamp: Any,
) -> None:
    """Mark a CSV import as completed and store parsed row counters."""

    cursor.execute(
        """
        UPDATE csv_imports
        SET
            records_saved = %s,
            records_rejected = %s,
            first_timestamp = %s,
            last_timestamp = %s,
            status = 'completed',
            error_message = NULL
        WHERE id = %s
        """,
        (
            records_saved,
            records_rejected,
            first_timestamp,
            last_timestamp,
            import_id,
        ),
    )


def fail_csv_import(
    cursor,
    *,
    import_id: int,
    error_message: str,
) -> None:
    """Mark a CSV import as failed with a truncated error message."""

    cursor.execute(
        """
        UPDATE csv_imports
        SET
            status = 'failed',
            error_message = %s
        WHERE id = %s
        """,
        (
            error_message[:5000],
            import_id,
        ),
    )


# =========================================================
# FIT IMPORT METADATA
# =========================================================

def find_fit_import(
    cursor,
    *,
    session_id: str,
    file_hash: str,
) -> dict[str, Any] | None:
    """Find an existing FIT import by session and file hash."""

    cursor.execute(
        """
        SELECT
            id,
            session_id,
            user_id,
            filename,
            file_hash,
            records_parsed,
            records_saved,
            records_rejected,
            status,
            error_message,
            first_timestamp,
            last_timestamp,
            parser_version,
            imported_at
        FROM fit_imports
        WHERE session_id = %s
          AND file_hash = %s
        LIMIT 1
        """,
        (
            session_id,
            file_hash,
        ),
    )

    row = cursor.fetchone()

    if not row:
        return None

    return {
        "id": row[0],
        "session_id": row[1],
        "user_id": row[2],
        "filename": row[3],
        "file_hash": row[4],
        "records_parsed": row[5],
        "records_saved": row[6],
        "records_rejected": row[7],
        "status": row[8],
        "error_message": row[9],
        "first_timestamp": row[10],
        "last_timestamp": row[11],
        "parser_version": row[12],
        "imported_at": row[13],
    }


def list_session_data_sources(
    cursor,
    *,
    session_id: str,
    user_id: str,
) -> list[dict[str, Any]]:
    """Return import provenance and retained-signal facts for one session."""

    cursor.execute(
        """
        SELECT *
        FROM (
            SELECT
                fi.id AS import_id,
                fi.import_type,
                fi.filename,
                fi.file_hash,
                fi.device_model,
                fi.device_type,
                fi.measurement_method,
                fi.parser_version,
                fi.source_timezone,
                fi.first_timestamp,
                fi.last_timestamp,
                fi.records_saved,
                fi.status,
                fi.imported_at,
                EXISTS (
                    SELECT 1 FROM fit_data fd
                    WHERE fd.import_id = fi.id
                      AND (fd.rr_interval IS NOT NULL
                        OR COALESCE(jsonb_array_length(fd.rr_intervals_json), 0) > 0)
                ) AS has_raw_rr
            FROM fit_imports fi
            WHERE fi.session_id = %s AND fi.user_id = %s
            UNION ALL
            SELECT
                ci.id AS import_id,
                'csv' AS import_type,
                ci.filename,
                ci.file_hash,
                ci.device_model,
                ci.device_type,
                ci.measurement_method,
                ci.parser_version,
                ci.source_timezone,
                ci.first_timestamp,
                ci.last_timestamp,
                ci.records_saved,
                ci.status,
                ci.imported_at,
                false AS has_raw_rr
            FROM csv_imports ci
            WHERE ci.session_id = %s AND ci.user_id = %s
        ) sources
        ORDER BY first_timestamp NULLS LAST, import_id
        """,
        (session_id, user_id, session_id, user_id),
    )
    columns = [column.name for column in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def create_fit_import(
    cursor,
    *,
    session_id: str,
    user_id: str,
    filename: str,
    file_hash: str,
    file_size: int,
    records_parsed: int,
    parser_version: str,
    manufacturer: str | None = None,
    product: str | None = None,
    device_serial: str | None = None,
    device_type: str | None = None,
    device_model: str | None = None,
    measurement_method: str | None = None,
    telemetry_schema_version: str | None = None,
    source_timezone: str | None = None,
    timestamp_normalization_version: str | None = None,
    import_type: str = "fit",
) -> int:
    """Create wearable telemetry metadata in the FIT-compatible store."""

    cursor.execute(
        """
        INSERT INTO fit_imports (
            session_id,
            user_id,
            filename,
            file_hash,
            file_size,
            records_parsed,
            records_saved,
            records_rejected,
            parser_version,
            manufacturer,
            product,
            device_serial,
            device_type,
            device_model,
            measurement_method,
            telemetry_schema_version,
            source_timezone,
            timestamp_normalization_version,
            import_type,
            status
        )
        VALUES (
            %s, %s, %s, %s, %s,
            %s, 0, 0, %s,
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'processing'
        )
        RETURNING id
        """,
        (
            session_id,
            user_id,
            filename,
            file_hash,
            file_size,
            records_parsed,
            parser_version,
            manufacturer,
            product,
            device_serial,
            device_type,
            device_model,
            measurement_method,
            telemetry_schema_version,
            source_timezone,
            timestamp_normalization_version,
            import_type,
        ),
    )

    return cursor.fetchone()[0]


def complete_fit_import(
    cursor,
    *,
    import_id: int,
    records_saved: int,
    records_rejected: int,
    first_timestamp: Any,
    last_timestamp: Any,
) -> None:
    """Mark a FIT import as completed and store parsed row counters."""

    cursor.execute(
        """
        UPDATE fit_imports
        SET
            records_saved = %s,
            records_rejected = %s,
            first_timestamp = %s,
            last_timestamp = %s,
            status = 'completed',
            error_message = NULL
        WHERE id = %s
        """,
        (
            records_saved,
            records_rejected,
            first_timestamp,
            last_timestamp,
            import_id,
        ),
    )


def fail_fit_import(
    cursor,
    *,
    import_id: int,
    error_message: str,
) -> None:
    """Mark a FIT import as failed with a truncated error message."""

    cursor.execute(
        """
        UPDATE fit_imports
        SET
            status = 'failed',
            error_message = %s
        WHERE id = %s
        """,
        (
            error_message[:5000],
            import_id,
        ),
    )

# =========================================================
# CSV MEASUREMENTS
# =========================================================

def insert_csv_measurements(
    cursor,
    *,
    import_id: int,
    session_id: str,
    user_id: str,
    filename: str,
    rows: list[dict[str, Any]],
    telemetry_metadata: dict[str, str],
) -> int:
    """
    Performs a bulk insert using psycopg2 execute_values.
    Considerably faster than executing one INSERT per row.
    """

    if not rows:
        return 0

    values = []

    for row in rows:
        pulse = row.get("pulse")
        heart_rate = row.get("heart_rate_bpm")

        reported_hrv = (
            row.get("hrv")
            or row.get("device_reported_hrv_sdnn_ms")
            or row.get("device_reported_hrv_rmssd_ms")
        )
        values.append(
            (
                import_id,
                session_id,
                user_id,
                row.get("timestamp"),
                pulse,
                heart_rate,
                row.get("spo2"),
                row.get("motion"),
                row.get("o2_reminder"),
                row.get("pr_reminder"),
                row.get("source", "pulseox"),
                filename,
                json.dumps(row, default=str),
                row.get("pulse_rate_bpm") or pulse,
                heart_rate,
                telemetry_metadata["device_type"],
                row.get("device") or "checkme_o2",
                telemetry_metadata["measurement_method"],
                telemetry_metadata["signal_quality"],
                telemetry_metadata["quality_reason"],
                row.get("original_timestamp"),
                row.get("source_timezone"),
                row.get("timestamp_utc"),
            )
        )

    execute_values(
        cursor,
        """
        INSERT INTO csv_data (
            import_id,
            session_id,
            user_id,
            timestamp,
            pulse,
            heart_rate,
            spo2,
            motion,
            o2_reminder,
            pr_reminder,
            source,
            filename,
            raw_json,
            pulse_rate_bpm,
            heart_rate_bpm,
            device_type,
            device_model,
            measurement_method,
            signal_quality,
            quality_reason,
            original_timestamp,
            source_timezone,
            timestamp_utc
        )
        VALUES %s
        """,
        values,
        page_size=1000,
    )

    return len(values)


def load_csv(
    cursor,
    *,
    session_id: str,
    import_id: int | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    limit_clause = ""
    params: list[Any]

    if limit is not None:
        limit_clause = "LIMIT %s"

    if import_id is not None:
        params = [
            session_id,
            import_id,
        ]

        if limit is not None:
            params.append(limit)

        cursor.execute(
            f"""
            SELECT
                timestamp,
                pulse,
                heart_rate,
                spo2,
                motion,
                o2_reminder,
                pr_reminder,
                source,
                pulse_rate_bpm,
                heart_rate_bpm,
                device_type,
                device_model,
                measurement_method,
                signal_quality,
                quality_reason,
                original_timestamp,
                source_timezone,
                timestamp_utc
            FROM csv_data
            WHERE session_id = %s
              AND import_id = %s
            ORDER BY timestamp ASC, id ASC
            {limit_clause}
            """,
            params,
        )

    else:
        params = [session_id]

        if limit is not None:
            params.append(limit)

        cursor.execute(
            f"""
            SELECT
                timestamp,
                pulse,
                heart_rate,
                spo2,
                motion,
                o2_reminder,
                pr_reminder,
                source,
                pulse_rate_bpm,
                heart_rate_bpm,
                device_type,
                device_model,
                measurement_method,
                signal_quality,
                quality_reason,
                original_timestamp,
                source_timezone,
                timestamp_utc
            FROM csv_data
            WHERE session_id = %s
            ORDER BY timestamp ASC, id ASC
            {limit_clause}
            """,
            params,
        )

    rows = cursor.fetchall()

    return [
        {
            "timestamp": row[0],
            "time": row[0],
            "pulse": row[8] if row[8] is not None else row[1],
            "pulse_rate_bpm": row[8] if row[8] is not None else row[1],
            # Historical CSV imports copied pulse into heart_rate. Do not
            # revive that ambiguity in the canonical telemetry contract.
            "heart_rate": row[9],
            "heart_rate_bpm": row[9],
            "spo2": row[3],
            "motion": row[4],
            "o2_reminder": row[5],
            "pr_reminder": row[6],
            "source": row[7] or "pulseox",
            "device_type": row[10] or "unknown",
            "device_model": row[11],
            "measurement_method": row[12] or "unknown",
            "signal_quality": row[13] or "unknown",
            "quality_reason": row[14],
            "original_timestamp": row[15],
            "source_timezone": row[16] or "unknown",
            "timestamp_utc": row[17],
        }
        for row in rows
    ]


# =========================================================
# FIT MEASUREMENTS
# =========================================================

def insert_fit_measurements(
    cursor,
    *,
    import_id: int,
    session_id: str,
    user_id: str,
    filename: str,
    rows: list[dict[str, Any]],
    telemetry_metadata: dict[str, str],
) -> int:
    """Bulk insert FIT wearable measurements for one import."""

    if not rows:
        return 0

    values = []

    for row in rows:
        heart_rate = row.get("heart_rate_bpm")
        pulse = row.get("pulse_rate_bpm")
        reported_hrv = (
            row.get("hrv")
            or row.get("device_reported_hrv_sdnn_ms")
            or row.get("device_reported_hrv_rmssd_ms")
        )

        values.append(
            (
                import_id,
                session_id,
                user_id,
                row.get("timestamp"),
                heart_rate,
                pulse,
                heart_rate,
                row.get("spo2"),
                row.get("rr_interval"),
                reported_hrv,
                row.get("source", "fit"),
                filename,
                json.dumps(row, default=str),
                pulse,
                heart_rate,
                telemetry_metadata["device_type"],
                row.get("device_model") or row.get("device") or "fit_compatible_wearable",
                telemetry_metadata["measurement_method"],
                telemetry_metadata["signal_quality"],
                telemetry_metadata["quality_reason"],
                row.get("original_timestamp"),
                row.get("source_timezone"),
                row.get("timestamp_utc"),
                json.dumps(row.get("rr_intervals") or []),
                "source_native",
            )
        )

    execute_values(
        cursor,
        """
        INSERT INTO fit_data (
            import_id,
            session_id,
            user_id,
            timestamp,
            heart_rate,
            pulse,
            hr,
            spo2,
            rr_interval,
            hrv,
            source,
            filename,
            raw_json,
            pulse_rate_bpm,
            heart_rate_bpm,
            device_type,
            device_model,
            measurement_method,
            signal_quality,
            quality_reason,
            original_timestamp,
            source_timezone,
            timestamp_utc,
            rr_intervals_json,
            rr_unit
        )
        VALUES %s
        """,
        values,
        page_size=1000,
    )

    return len(values)


def load_fit(
    cursor,
    *,
    session_id: str,
    import_id: int | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    limit_clause = ""
    params: list[Any]

    if limit is not None:
        limit_clause = "LIMIT %s"

    if import_id is not None:
        params = [
            session_id,
            import_id,
        ]

        if limit is not None:
            params.append(limit)

        cursor.execute(
            f"""
            SELECT
                timestamp,
                heart_rate,
                pulse,
                hr,
                spo2,
                rr_interval,
                hrv,
                source,
                pulse_rate_bpm,
                heart_rate_bpm,
                device_type,
                device_model,
                measurement_method,
                signal_quality,
                quality_reason,
                original_timestamp,
                source_timezone,
                timestamp_utc,
                rr_intervals_json,
                rr_unit
            FROM fit_data
            WHERE session_id = %s
              AND import_id = %s
            ORDER BY timestamp ASC, id ASC
            {limit_clause}
            """,
            params,
        )

    else:
        params = [session_id]

        if limit is not None:
            params.append(limit)

        cursor.execute(
            f"""
            SELECT
                timestamp,
                heart_rate,
                pulse,
                hr,
                spo2,
                rr_interval,
                hrv,
                source,
                pulse_rate_bpm,
                heart_rate_bpm,
                device_type,
                device_model,
                measurement_method,
                signal_quality,
                quality_reason,
                original_timestamp,
                source_timezone,
                timestamp_utc,
                rr_intervals_json,
                rr_unit
            FROM fit_data
            WHERE session_id = %s
            ORDER BY timestamp ASC, id ASC
            {limit_clause}
            """,
            params,
        )

    rows = cursor.fetchall()

    return [
        {
            "timestamp": row[0],
            "time": row[0],
            "heart_rate": first_not_none(row[9], row[1], row[3]),
            "heart_rate_bpm": first_not_none(row[9], row[1], row[3]),
            # Earlier FIT rows duplicated HR in pulse; only explicit pulse
            # values are exposed as pulse-rate telemetry.
            "pulse": row[8],
            "pulse_rate_bpm": row[8],
            "hr": first_not_none(
                row[3],
                row[1],
                row[2],
            ),
            "spo2": row[4],
            "rr_interval": row[5],
            "hrv": row[6],
            "source": row[7] or "fit",
            "device_type": row[10] or "unknown",
            "device_model": row[11],
            "measurement_method": row[12] or "unknown",
            "signal_quality": row[13] or "unknown",
            "quality_reason": row[14],
            "original_timestamp": row[15],
            "source_timezone": row[16] or "unknown",
            "timestamp_utc": row[17],
            "rr_intervals": decode_json_list(row[18]),
            "rr_unit": row[19] or "unknown",
        }
        for row in rows
    ]


# =========================================================
# IMPORT LOOKUPS
# =========================================================

def get_latest_completed_csv_import(
    cursor,
    *,
    session_id: str,
) -> dict[str, Any] | None:
    """Return the newest completed CSV import for a session."""

    cursor.execute(
        """
        SELECT
            id,
            session_id,
            user_id,
            filename,
            file_hash,
            records_saved,
            first_timestamp,
            last_timestamp
        FROM csv_imports
        WHERE session_id = %s
          AND status = 'completed'
        ORDER BY imported_at DESC, id DESC
        LIMIT 1
        """,
        (session_id,),
    )

    row = cursor.fetchone()

    if not row:
        return None

    return {
        "id": row[0],
        "session_id": row[1],
        "user_id": row[2],
        "filename": row[3],
        "file_hash": row[4],
        "records_saved": row[5],
        "first_timestamp": row[6],
        "last_timestamp": row[7],
    }


def get_latest_completed_fit_import(
    cursor,
    *,
    session_id: str,
) -> dict[str, Any] | None:
    """Return the newest completed FIT import for a session."""

    cursor.execute(
        """
        SELECT
            id,
            session_id,
            user_id,
            filename,
            file_hash,
            records_saved,
            first_timestamp,
            last_timestamp
        FROM fit_imports
        WHERE session_id = %s
          AND status = 'completed'
        ORDER BY imported_at DESC, id DESC
        LIMIT 1
        """,
        (session_id,),
    )

    row = cursor.fetchone()

    if not row:
        return None

    return {
        "id": row[0],
        "session_id": row[1],
        "user_id": row[2],
        "filename": row[3],
        "file_hash": row[4],
        "records_saved": row[5],
        "first_timestamp": row[6],
        "last_timestamp": row[7],
    }


# =========================================================
# HELPERS
# =========================================================

def decode_json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if not value:
        return []
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        return []
    return decoded if isinstance(decoded, list) else []


def first_not_none(*values):
    """Choose the first available value from equivalent telemetry columns."""

    for value in values:
        if value is not None:
            return value

    return None
