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
            status
        )
        VALUES (
            %s, %s, %s, %s, %s,
            0, 0, %s, %s, 'processing'
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
) -> int:
    """Create a FIT import metadata row in processing state."""

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
            status
        )
        VALUES (
            %s, %s, %s, %s, %s,
            %s, 0, 0, %s,
            %s, %s, %s, 'processing'
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
        heart_rate = row.get("heart_rate") or pulse

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
            raw_json
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
                source
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
                source
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
            "pulse": row[1] if row[1] is not None else row[2],
            "heart_rate": (
                row[2]
                if row[2] is not None
                else row[1]
            ),
            "spo2": row[3],
            "motion": row[4],
            "o2_reminder": row[5],
            "pr_reminder": row[6],
            "source": row[7] or "pulseox",
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
) -> int:
    """Bulk insert FIT wearable measurements for one import."""

    if not rows:
        return 0

    values = []

    for row in rows:
        heart_rate = (
            row.get("heart_rate")
            or row.get("pulse")
            or row.get("hr")
        )

        pulse = (
            row.get("pulse")
            or row.get("heart_rate")
            or row.get("hr")
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
                row.get("hrv"),
                row.get("source", "fit"),
                filename,
                json.dumps(row, default=str),
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
            raw_json
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
                source
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
                source
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
            "heart_rate": first_not_none(
                row[1],
                row[2],
                row[3],
            ),
            "pulse": first_not_none(
                row[2],
                row[1],
                row[3],
            ),
            "hr": first_not_none(
                row[3],
                row[1],
                row[2],
            ),
            "spo2": row[4],
            "rr_interval": row[5],
            "hrv": row[6],
            "source": row[7] or "fit",
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

def first_not_none(*values):
    """Choose the first available value from equivalent telemetry columns."""

    for value in values:
        if value is not None:
            return value

    return None
