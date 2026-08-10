"""SQL helpers for merge jobs and synchronized telemetry rows.

The service layer controls commit/rollback; this file only translates between
Python dictionaries and PostgreSQL tables used by the merge pipeline.
"""

from __future__ import annotations

import json
from typing import Any

from psycopg2.extras import execute_values


def create_merge_job(
    cursor,
    *,
    session_id: str,
    user_id: str,
    fit_import_id: int | None,
    csv_import_id: int,
    fit_records: int,
    csv_records: int,
    algorithm: str,
    tolerance_ms: int,
) -> int:
    """Create a merge job record before inserting synchronized rows."""

    cursor.execute(
        """
        INSERT INTO merge_jobs (
            session_id,
            user_id,
            fit_import_id,
            csv_import_id,
            fit_records,
            csv_records,
            merged_records,
            algorithm,
            tolerance_ms,
            status
        )
        VALUES (
            %s, %s, %s, %s,
            %s, %s, 0, %s, %s, 'RUNNING'
        )
        RETURNING merge_id
        """,
        (
            session_id,
            user_id,
            fit_import_id,
            csv_import_id,
            fit_records,
            csv_records,
            algorithm,
            tolerance_ms,
        ),
    )

    return cursor.fetchone()[0]


def complete_merge_job(
    cursor,
    *,
    merge_id: int,
    merged_records: int,
    notes: str | None = None,
    time_alignment_method: str | None = None,
    time_alignment_quality: str | None = None,
) -> None:
    """Mark a merge job as completed after rows are inserted."""

    cursor.execute(
        """
        UPDATE merge_jobs
        SET
            merged_records = %s,
            status = 'COMPLETED',
            finished_at = CURRENT_TIMESTAMP,
            notes = COALESCE(%s, notes),
            time_alignment_method = COALESCE(%s, time_alignment_method),
            time_alignment_quality = COALESCE(%s, time_alignment_quality)
        WHERE merge_id = %s
        """,
        (
            merged_records,
            notes,
            time_alignment_method,
            time_alignment_quality,
            merge_id,
        ),
    )


def fail_merge_job(
    cursor,
    *,
    merge_id: int,
    error_message: str,
) -> None:
    """Mark a merge job as failed and store diagnostic notes."""

    cursor.execute(
        """
        UPDATE merge_jobs
        SET
            status = 'FAILED',
            notes = %s,
            finished_at = CURRENT_TIMESTAMP
        WHERE merge_id = %s
        """,
        (
            error_message[:5000],
            merge_id,
        ),
    )


def insert_merged_measurements(
    cursor,
    *,
    merge_id: int,
    session_id: str,
    user_id: str,
    rows: list[dict[str, Any]],
) -> int:
    """Bulk insert synchronized FIT/CSV measurements."""

    if not rows:
        return 0

    values = [
        (
            merge_id,
            session_id,
            user_id,
            row.get("timestamp"),
            "during",

            row.get("heart_rate"),
            row.get("heart_rate_bpm"),
            row.get("hrv"),
            row.get("rr_interval"),
            json.dumps(row.get("rr_intervals") or []),

            row.get("spo2"),
            row.get("pulse"),
            row.get("pulse_rate_bpm"),
            row.get("motion"),

            row.get("hr_source_type"),
            row.get("hr_measurement_method"),
            row.get("hr_signal_quality"),
            row.get("pulse_source_type"),
            row.get("pulse_measurement_method"),
            row.get("pulse_signal_quality"),
            row.get("telemetry_schema_version"),
            row.get("timestamp_utc"),
            row.get("fit_timestamp_utc"),
            row.get("csv_timestamp_utc"),
            row.get("time_alignment_method"),
            row.get("time_alignment_quality"),

            row.get("fit_timestamp"),
            row.get("csv_timestamp"),
            row.get("delta_ms"),
            bool(row.get("synchronized")),
        )
        for row in rows
    ]

    execute_values(
        cursor,
        """
        INSERT INTO merged_data (
            merge_id,
            session_id,
            user_id,
            timestamp,
            phase,

            heart_rate,
            heart_rate_bpm,
            hrv,
            rr_interval,
            rr_intervals_json,

            spo2,
            pulse,
            pulse_rate_bpm,
            motion,
            hr_source_type,
            hr_measurement_method,
            hr_signal_quality,
            pulse_source_type,
            pulse_measurement_method,
            pulse_signal_quality,
            telemetry_schema_version,
            timestamp_utc,
            fit_timestamp_utc,
            csv_timestamp_utc,
            time_alignment_method,
            time_alignment_quality,

            fit_timestamp,
            csv_timestamp,
            delta_ms,
            synchronized
        )
        VALUES %s
        """,
        values,
        page_size=1000,
    )

    return len(values)


def get_latest_completed_merge_job(
    cursor,
    *,
    session_id: str,
) -> dict[str, Any] | None:
    """Return the newest completed merge job for a session."""

    cursor.execute(
        """
        SELECT
            merge_id,
            session_id,
            user_id,
            fit_import_id,
            csv_import_id,
            fit_records,
            csv_records,
            merged_records,
            algorithm,
            tolerance_ms,
            notes,
            started_at,
            finished_at
        FROM merge_jobs
        WHERE session_id = %s
          AND status = 'COMPLETED'
        ORDER BY finished_at DESC, merge_id DESC
        LIMIT 1
        """,
        (session_id,),
    )

    row = cursor.fetchone()

    if not row:
        return None

    return {
        "merge_id": row[0],
        "session_id": row[1],
        "user_id": row[2],
        "fit_import_id": row[3],
        "csv_import_id": row[4],
        "fit_records": row[5],
        "csv_records": row[6],
        "merged_records": row[7],
        "algorithm": row[8],
        "tolerance_ms": row[9],
        "notes": row[10],
        "started_at": row[11],
        "finished_at": row[12],
    }


def load_merged_measurements(
    cursor,
    *,
    merge_id: int,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Load synchronized measurements for a merge job in timeline order."""

    limit_clause = ""
    params: list[Any] = [merge_id]

    if limit is not None:
        limit_clause = "LIMIT %s"
        params.append(limit)

    cursor.execute(
        f"""
        SELECT
            timestamp,
            heart_rate,
            heart_rate_bpm,
            hrv,
            rr_interval,
            rr_intervals_json,
            spo2,
            pulse,
            pulse_rate_bpm,
            motion,

            hr_source_type,
            hr_measurement_method,
            hr_signal_quality,
            pulse_source_type,
            pulse_measurement_method,
            pulse_signal_quality,
            telemetry_schema_version,
            timestamp_utc,
            fit_timestamp_utc,
            csv_timestamp_utc,
            time_alignment_method,
            time_alignment_quality,
            fit_timestamp,
            csv_timestamp,
            delta_ms,
            synchronized
        FROM merged_data
        WHERE merge_id = %s
        ORDER BY timestamp ASC, id ASC
        {limit_clause}
        """,
        params,
    )

    return [
        {
            "timestamp": row[0],
            "heart_rate": row[1],
            "heart_rate_bpm": row[2] if row[2] is not None else row[1],
            "hrv": row[3],
            "rr_interval": row[4],
            "rr_intervals": decode_json_list(row[5]),
            "spo2": row[6],
            "pulse": row[7],
            "pulse_rate_bpm": row[8] if row[8] is not None else row[7],
            "motion": row[9],
            "hr_source_type": row[10] or "unknown",
            "hr_measurement_method": row[11] or "unknown",
            "hr_signal_quality": row[12] or "unknown",
            "pulse_source_type": row[13] or "unknown",
            "pulse_measurement_method": row[14] or "unknown",
            "pulse_signal_quality": row[15] or "unknown",
            "telemetry_schema_version": row[16],
            "timestamp_utc": row[17],
            "fit_timestamp_utc": row[18],
            "csv_timestamp_utc": row[19],
            "time_alignment_method": row[20] or "unknown",
            "time_alignment_quality": row[21] or "unknown",
            "fit_timestamp": row[22],
            "csv_timestamp": row[23],
            "delta_ms": row[24],
            "synchronized": bool(row[25]),
        }
        for row in cursor.fetchall()
    ]


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
