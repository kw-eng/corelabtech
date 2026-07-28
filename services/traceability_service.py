"""Operational traceability assembly for wellness sessions."""

from __future__ import annotations

from typing import Any

from database_postgres import db


def isoformat_or_none(value):
    if not value:
        return None

    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def normalize_process_status(value: str | None) -> str:
    normalized = str(value or "").strip().lower()

    if normalized in {"completed", "complete", "success", "saved"}:
        return "completed"

    if normalized in {"failed", "error", "rejected"}:
        return "failed"

    if normalized in {"running", "processing", "queued"}:
        return "in_progress"

    return "pending"


def build_trace_step(
    *,
    key: str,
    label: str,
    status: str,
    timestamp=None,
    detail: str | None = None,
    metadata: dict | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "status": status,
        "timestamp": isoformat_or_none(timestamp),
        "detail": detail,
        "metadata": metadata or {},
    }


def get_session_traceability(
    *,
    session: dict[str, Any],
) -> dict[str, Any]:
    """Return an operational trace for one already-authorized session."""

    session_id = str(session.get("session_id") or "").strip()
    client_id = session.get("client_id") or session.get("user_id")

    connection = db()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT filename, status, records_saved, records_rejected,
                   imported_at, error_message
            FROM fit_imports
            WHERE session_id = %s
            ORDER BY imported_at DESC, id DESC
            LIMIT 1
            """,
            (session_id,),
        )
        fit_row = cursor.fetchone()

        cursor.execute(
            """
            SELECT filename, status, records_saved, records_rejected,
                   imported_at, error_message
            FROM csv_imports
            WHERE session_id = %s
            ORDER BY imported_at DESC, id DESC
            LIMIT 1
            """,
            (session_id,),
        )
        csv_row = cursor.fetchone()

        cursor.execute(
            """
            SELECT merge_id, status, started_at, finished_at,
                   fit_records, csv_records, merged_records, notes
            FROM merge_jobs
            WHERE session_id = %s
            ORDER BY COALESCE(finished_at, started_at) DESC, merge_id DESC
            LIMIT 1
            """,
            (session_id,),
        )
        merge_row = cursor.fetchone()

        cursor.execute(
            """
            SELECT ai_result_id, overall_score, data_quality_score,
                   anomaly_detected, created_at
            FROM ai_results
            WHERE session_id = %s
            ORDER BY created_at DESC, ai_result_id DESC
            LIMIT 1
            """,
            (session_id,),
        )
        ai_row = cursor.fetchone()

        cursor.execute(
            """
            SELECT audit_id, actor_user_id, actor_role, action,
                   entity_type, entity_id, client_id, session_id,
                   outcome, details_json, created_at
            FROM audit_log
            WHERE session_id = %s
               OR (entity_type = 'session' AND entity_id = %s)
            ORDER BY created_at DESC, audit_id DESC
            LIMIT 20
            """,
            (session_id, session_id),
        )
        audit_rows = cursor.fetchall()

    finally:
        cursor.close()
        connection.close()

    report_export_row = next(
        (
            row
            for row in audit_rows
            if row[3] == "report.export" and row[8] == "success"
        ),
        None,
    )

    fit_status = normalize_process_status(fit_row[1] if fit_row else None)
    csv_status = normalize_process_status(csv_row[1] if csv_row else None)
    merge_status = normalize_process_status(merge_row[1] if merge_row else None)
    report_status = "completed" if report_export_row else "pending"

    steps = [
        build_trace_step(
            key="session_created",
            label="Session created",
            status="completed",
            timestamp=session.get("created_at"),
            detail=f"Client {client_id}",
        ),
        build_trace_step(
            key="fit_imported",
            label="HR/HRV data imported",
            status=fit_status,
            timestamp=fit_row[4] if fit_row else None,
            detail=fit_row[0] if fit_row else "Waiting for FIT import",
            metadata={
                "records_saved": fit_row[2] if fit_row else 0,
                "records_rejected": fit_row[3] if fit_row else 0,
                "error": fit_row[5] if fit_row else None,
            },
        ),
        build_trace_step(
            key="csv_imported",
            label="SpO2/pulse data imported",
            status=csv_status,
            timestamp=csv_row[4] if csv_row else None,
            detail=csv_row[0] if csv_row else "Waiting for CSV import",
            metadata={
                "records_saved": csv_row[2] if csv_row else 0,
                "records_rejected": csv_row[3] if csv_row else 0,
                "error": csv_row[5] if csv_row else None,
            },
        ),
        build_trace_step(
            key="merge_completed",
            label="Synchronization completed",
            status=merge_status,
            timestamp=(merge_row[3] or merge_row[2] if merge_row else None),
            detail=(
                f"{merge_row[6]} merged samples"
                if merge_row
                else "Waiting for synchronized telemetry"
            ),
            metadata={
                "merge_id": merge_row[0] if merge_row else None,
                "fit_records": merge_row[4] if merge_row else 0,
                "csv_records": merge_row[5] if merge_row else 0,
                "merged_records": merge_row[6] if merge_row else 0,
                "notes": merge_row[7] if merge_row else None,
            },
        ),
        build_trace_step(
            key="ai_generated",
            label="AI wellness analysis generated",
            status="completed" if ai_row else "pending",
            timestamp=ai_row[4] if ai_row else None,
            detail=(
                f"Score {ai_row[1]:.0f}/100"
                if ai_row and ai_row[1] is not None
                else "Waiting for wellness analysis"
            ),
            metadata={
                "ai_result_id": ai_row[0] if ai_row else None,
                "overall_score": ai_row[1] if ai_row else None,
                "data_quality_score": ai_row[2] if ai_row else None,
                "anomaly_detected": bool(ai_row[3]) if ai_row else False,
            },
        ),
        build_trace_step(
            key="report_exported",
            label="PDF report exported",
            status=report_status,
            timestamp=report_export_row[10] if report_export_row else None,
            detail=(
                "Session report export recorded"
                if report_export_row
                else "Not exported yet"
            ),
            metadata={
                "audit_id": report_export_row[0] if report_export_row else None,
                "actor_user_id": (
                    report_export_row[1] if report_export_row else None
                ),
                "actor_role": report_export_row[2] if report_export_row else None,
            },
        ),
    ]

    return {
        "status": "ok",
        "session_id": session_id,
        "client_id": client_id,
        "report_exported": report_status == "completed",
        "steps": steps,
        "events": [
            {
                "audit_id": row[0],
                "actor_user_id": row[1],
                "actor_role": row[2],
                "action": row[3],
                "entity_type": row[4],
                "entity_id": row[5],
                "client_id": row[6],
                "session_id": row[7],
                "outcome": row[8],
                "details": row[9] or {},
                "created_at": isoformat_or_none(row[10]),
            }
            for row in audit_rows
        ],
    }
