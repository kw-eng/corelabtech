"""SQL helpers for persisted AI analysis results."""

from __future__ import annotations

import json
from typing import Any


def create_ai_result(
    cursor,
    *,
    merge_id: int,
    session_id: str,
    user_id: str,
    model_name: str,
    model_version: str,
) -> int:
    """Create an empty AI result row before deterministic scoring runs."""

    cursor.execute(
        """
        INSERT INTO ai_results (
            merge_id,
            session_id,
            user_id,
            model_name,
            model_version,
            features_json,
            result_json
        )
        VALUES (
            %s, %s, %s, %s, %s,
            '{}'::jsonb,
            '{}'::jsonb
        )
        RETURNING ai_result_id
        """,
        (
            merge_id,
            session_id,
            user_id,
            model_name,
            model_version,
        ),
    )

    return cursor.fetchone()[0]


def complete_ai_result(
    cursor,
    *,
    ai_result_id: int,
    result: dict[str, Any],
) -> None:
    """Persist scores, flags, summary text and raw result JSON."""

    cursor.execute(
        """
        UPDATE ai_results
        SET
            overall_score = %s,
            recovery_score = %s,
            stress_score = %s,
            hypoxia_score = %s,
            cardiovascular_score = %s,
            data_quality_score = %s,

            anomaly_detected = %s,
            stress_detected = %s,
            hypoxia_detected = %s,
            arrhythmia_detected = %s,

            summary = %s,
            recommendations = %s,

            features_json = %s::jsonb,
            result_json = %s::jsonb
        WHERE ai_result_id = %s
        """,
        (
            result.get("overall_score"),
            result.get("recovery_score"),
            result.get("stress_score"),
            result.get("hypoxia_score"),
            result.get("cardiovascular_score"),
            result.get("data_quality_score"),

            bool(result.get("anomaly_detected")),
            bool(result.get("stress_detected")),
            bool(result.get("hypoxia_detected")),
            bool(result.get("arrhythmia_detected")),

            result.get("summary"),
            result.get("recommendations"),

            json.dumps(
                result.get("features", {}),
                default=str,
            ),
            json.dumps(result, default=str),

            ai_result_id,
        ),
    )


def get_latest_ai_result(
    cursor,
    *,
    session_id: str,
) -> dict[str, Any] | None:
    """Return the newest AI result for dashboard/API consumers."""

    cursor.execute(
        """
        SELECT
            ai_result_id,
            merge_id,
            session_id,
            user_id,
            model_name,
            model_version,
            overall_score,
            recovery_score,
            stress_score,
            hypoxia_score,
            cardiovascular_score,
            data_quality_score,
            anomaly_detected,
            stress_detected,
            hypoxia_detected,
            summary,
            recommendations,
            features_json,
            result_json,
            created_at
        FROM ai_results
        WHERE session_id = %s
        ORDER BY created_at DESC, ai_result_id DESC
        LIMIT 1
        """,
        (session_id,),
    )

    row = cursor.fetchone()

    if not row:
        return None

    return {
        "ai_result_id": row[0],
        "merge_id": row[1],
        "session_id": row[2],
        "user_id": row[3],
        "model_name": row[4],
        "model_version": row[5],
        "overall_score": row[6],
        "recovery_score": row[7],
        "stress_score": row[8],
        "hypoxia_score": row[9],
        "cardiovascular_score": row[10],
        "data_quality_score": row[11],
        "anomaly_detected": bool(row[12]),
        "stress_detected": bool(row[13]),
        "hypoxia_detected": bool(row[14]),
        "summary": row[15],
        "recommendations": row[16],
        "features": row[17] or {},
        "result": row[18] or {},
        "created_at": (
            row[19].isoformat()
            if row[19]
            else None
        ),
    }


def list_analyses(
    cursor,
    *,
    session_id: str,
) -> list[dict[str, Any]]:
    """List all saved analyses for a session, newest first."""

    cursor.execute(
        """
        SELECT
            ai_result_id,
            merge_id,
            session_id,
            user_id,
            model_name,
            model_version,
            overall_score,
            data_quality_score,
            anomaly_detected,
            summary,
            created_at
        FROM ai_results
        WHERE session_id = %s
        ORDER BY created_at DESC, ai_result_id DESC
        """,
        (session_id,),
    )

    return [
        {
            "ai_result_id": row[0],
            "merge_id": row[1],
            "session_id": row[2],
            "user_id": row[3],
            "model_name": row[4],
            "model_version": row[5],
            "overall_score": row[6],
            "data_quality_score": row[7],
            "anomaly_detected": bool(row[8]),
            "summary": row[9],
            "created_at": row[10].isoformat() if row[10] else None,
        }
        for row in cursor.fetchall()
    ]
