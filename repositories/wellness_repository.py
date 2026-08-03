"""SQL helpers for wellness session features and daily baselines."""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any


def upsert_session_features(
    cursor,
    *,
    session_id: str,
    user_id: str,
    phase: str,
    window_start: datetime | None,
    window_end: datetime | None,
    features: dict[str, Any],
    result: dict[str, Any],
    protocol_id: int,
    target_ata: float | None = None,
    actual_ata: float | None = None,
) -> None:
    """Persist one analyzed wellness feature row for a session."""

    cursor.execute(
        """
        INSERT INTO session_features (
            session_id,
            user_id,
            protocol_id,
            phase,
            window_start,
            window_end,
            avg_hr,
            min_hr,
            max_hr,
            avg_spo2,
            min_spo2,
            max_spo2,
            rmssd,
            sdnn,
            pnn50,
            rr_count,
            artifact_ratio,
            hr_response,
            spo2_drop,
            recovery_delta,
            deviation_from_baseline,
            status,
            data_quality_score,
            target_ata,
            actual_ata,
            hrv_algorithm_version,
            hrv_confidence,
            features_json
        )
        VALUES (
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s::jsonb
        )
        ON CONFLICT (session_id, phase, window_start, window_end)
        DO UPDATE SET
            user_id = EXCLUDED.user_id,
            protocol_id = EXCLUDED.protocol_id,
            avg_hr = EXCLUDED.avg_hr,
            min_hr = EXCLUDED.min_hr,
            max_hr = EXCLUDED.max_hr,
            avg_spo2 = EXCLUDED.avg_spo2,
            min_spo2 = EXCLUDED.min_spo2,
            max_spo2 = EXCLUDED.max_spo2,
            rmssd = EXCLUDED.rmssd,
            sdnn = EXCLUDED.sdnn,
            pnn50 = EXCLUDED.pnn50,
            rr_count = EXCLUDED.rr_count,
            artifact_ratio = EXCLUDED.artifact_ratio,
            hr_response = EXCLUDED.hr_response,
            spo2_drop = EXCLUDED.spo2_drop,
            recovery_delta = EXCLUDED.recovery_delta,
            deviation_from_baseline = EXCLUDED.deviation_from_baseline,
            status = EXCLUDED.status,
            data_quality_score = EXCLUDED.data_quality_score,
            target_ata = EXCLUDED.target_ata,
            actual_ata = EXCLUDED.actual_ata,
            hrv_algorithm_version = EXCLUDED.hrv_algorithm_version,
            hrv_confidence = EXCLUDED.hrv_confidence,
            features_json = EXCLUDED.features_json
        """,
        (
            session_id,
            user_id,
            protocol_id,
            phase,
            window_start,
            window_end,
            features.get("avg_heart_rate") or features.get("avg_pulse"),
            features.get("min_heart_rate") or features.get("min_pulse"),
            features.get("max_heart_rate") or features.get("max_pulse"),
            features.get("avg_spo2"),
            features.get("min_spo2"),
            features.get("max_spo2"),
            features.get("avg_hrv"),
            features.get("sdnn"),
            features.get("pnn50"),
            int(features.get("rr_count") or 0),
            features.get("artifact_ratio"),
            features.get("hr_response"),
            features.get("spo2_drop"),
            features.get("recovery_delta"),
            features.get("deviation_from_baseline"),
            result.get("wellness_status"),
            result.get("data_quality_score"),
            target_ata,
            actual_ata,
            features.get("hrv_algorithm_version"),
            features.get("hrv_confidence"),
            json.dumps(
                {
                    **features,
                    "wellness_flags": result.get("wellness_flags", {}),
                    "quality_warnings": result.get("quality_warnings", []),
                },
                default=str,
            ),
        ),
    )


def refresh_daily_baseline(
    cursor,
    *,
    user_id: str,
    baseline_date: date,
    protocol_id: int | None = None,
) -> dict[str, Any]:
    """Recalculate a rolling baseline for one client and protocol."""

    if protocol_id is None:
        cursor.execute(
            """
            SELECT protocol_id
            FROM session_features
            WHERE user_id = %s
            ORDER BY COALESCE(window_start, created_at) DESC, id DESC
            LIMIT 1
            """,
            (user_id,),
        )
        protocol_row = cursor.fetchone()
        protocol_id = protocol_row[0] if protocol_row else None

    if protocol_id is None:
        raise ValueError("protocol_id is required for baseline calculation")

    cursor.execute(
        """
        WITH source AS (
            SELECT *
        FROM session_features
        WHERE user_id = %s
          AND protocol_id = %s
          AND session_id NOT LIKE 'PIPELINE_VALIDATION_%%'
          AND COALESCE(window_start::date, created_at::date) <= %s
          AND COALESCE(window_start::date, created_at::date) >= %s::date - INTERVAL '29 days'
        ),
        aggregated AS (
            SELECT
                AVG(rmssd) FILTER (
                    WHERE COALESCE(window_start::date, created_at::date) = %s
                ) AS rmssd_avg,
                AVG(rmssd) FILTER (
                    WHERE COALESCE(window_start::date, created_at::date) >= %s::date - INTERVAL '6 days'
                ) AS rmssd_7d,
                AVG(rmssd) FILTER (
                    WHERE COALESCE(window_start::date, created_at::date) >= %s::date - INTERVAL '13 days'
                ) AS rmssd_14d,
                AVG(rmssd) AS rmssd_30d,
                AVG(min_hr) FILTER (
                    WHERE COALESCE(window_start::date, created_at::date) >= %s::date - INTERVAL '6 days'
                ) AS resting_hr_7d,
                AVG(min_hr) AS resting_hr,
                AVG(avg_spo2) AS spo2_avg,
                MIN(min_spo2) AS spo2_min,
                COUNT(*) FILTER (
                    WHERE COALESCE(window_start::date, created_at::date) >= %s::date - INTERVAL '6 days'
                ) AS sessions_count_7d,
                COUNT(*) FILTER (
                    WHERE COALESCE(window_start::date, created_at::date) >= %s::date - INTERVAL '13 days'
                ) AS sessions_count_14d,
                COUNT(*) AS sessions_count_30d,
                AVG(data_quality_score) AS data_quality_score,
                BOOL_OR(status = 'data_quality_warning') AS has_quality_warning,
                BOOL_OR(status = 'elevated_load') AS has_elevated_load
            FROM source
        )
        SELECT
            rmssd_avg,
            rmssd_7d,
            rmssd_14d,
            rmssd_30d,
            resting_hr,
            resting_hr_7d,
            spo2_avg,
            spo2_min,
            COALESCE(sessions_count_7d, 0),
            COALESCE(sessions_count_14d, 0),
            COALESCE(sessions_count_30d, 0),
            data_quality_score,
            CASE
                WHEN COALESCE(sessions_count_7d, 0) < 3 THEN 'data_quality_warning'
                WHEN COALESCE(has_quality_warning, false) THEN 'data_quality_warning'
                WHEN COALESCE(has_elevated_load, false) THEN 'elevated_load'
                ELSE 'baseline'
            END AS status
        FROM aggregated
        """,
        (
            user_id,
            protocol_id,
            baseline_date,
            baseline_date,
            baseline_date,
            baseline_date,
            baseline_date,
            baseline_date,
            baseline_date,
            baseline_date,
        ),
    )

    row = cursor.fetchone()

    baseline = {
        "user_id": user_id,
        "protocol_id": protocol_id,
        "baseline_date": baseline_date.isoformat(),
        "rmssd_avg": row[0] if row else None,
        "rmssd_7d": row[1] if row else None,
        "rmssd_14d": row[2] if row else None,
        "rmssd_30d": row[3] if row else None,
        "resting_hr": row[4] if row else None,
        "resting_hr_7d": row[5] if row else None,
        "spo2_avg": row[6] if row else None,
        "spo2_min": row[7] if row else None,
        "sessions_count_7d": row[8] if row else 0,
        "sessions_count_14d": row[9] if row else 0,
        "sessions_count_30d": row[10] if row else 0,
        "data_quality_score": row[11] if row else None,
        "status": row[12] if row else "data_quality_warning",
    }

    cursor.execute(
        """
        INSERT INTO daily_baselines (
            user_id,
            protocol_id,
            baseline_date,
            rmssd_avg,
            rmssd_7d,
            rmssd_14d,
            rmssd_30d,
            resting_hr,
            resting_hr_7d,
            spo2_avg,
            spo2_min,
            sessions_count_7d,
            sessions_count_14d,
            sessions_count_30d,
            data_quality_score,
            status,
            baseline_json
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s::jsonb
        )
        ON CONFLICT (user_id, baseline_date, protocol_id)
        DO UPDATE SET
            rmssd_avg = EXCLUDED.rmssd_avg,
            rmssd_7d = EXCLUDED.rmssd_7d,
            rmssd_14d = EXCLUDED.rmssd_14d,
            rmssd_30d = EXCLUDED.rmssd_30d,
            resting_hr = EXCLUDED.resting_hr,
            resting_hr_7d = EXCLUDED.resting_hr_7d,
            spo2_avg = EXCLUDED.spo2_avg,
            spo2_min = EXCLUDED.spo2_min,
            sessions_count_7d = EXCLUDED.sessions_count_7d,
            sessions_count_14d = EXCLUDED.sessions_count_14d,
            sessions_count_30d = EXCLUDED.sessions_count_30d,
            data_quality_score = EXCLUDED.data_quality_score,
            status = EXCLUDED.status,
            baseline_json = EXCLUDED.baseline_json
        """,
        (
            user_id,
            protocol_id,
            baseline_date,
            baseline["rmssd_avg"],
            baseline["rmssd_7d"],
            baseline["rmssd_14d"],
            baseline["rmssd_30d"],
            baseline["resting_hr"],
            baseline["resting_hr_7d"],
            baseline["spo2_avg"],
            baseline["spo2_min"],
            baseline["sessions_count_7d"],
            baseline["sessions_count_14d"],
            baseline["sessions_count_30d"],
            baseline["data_quality_score"],
            baseline["status"],
            json.dumps(baseline, default=str),
        ),
    )

    return baseline


def get_wellness_summary(
    cursor,
    *,
    user_id: str,
    limit: int = 5,
    protocol_id: int | None = None,
) -> dict[str, Any]:
    """Return wellness history for one client and one compatible protocol."""

    if protocol_id is None:
        cursor.execute(
            """
            SELECT protocol_id
            FROM full_sessions
            WHERE user_id = %s
              AND completed = 1
              AND session_id NOT LIKE 'PIPELINE_VALIDATION_%%'
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (user_id,),
        )
        protocol_row = cursor.fetchone()
        protocol_id = protocol_row[0] if protocol_row else None

    cursor.execute(
        """
        SELECT
            baseline_date,
            rmssd_avg,
            rmssd_7d,
            rmssd_14d,
            rmssd_30d,
            resting_hr,
            resting_hr_7d,
            spo2_avg,
            spo2_min,
            sessions_count_7d,
            sessions_count_14d,
            sessions_count_30d,
            data_quality_score,
            status,
            baseline_json
        FROM daily_baselines
        WHERE user_id = %s
          AND protocol_id = %s
        ORDER BY baseline_date DESC, id DESC
        LIMIT 1
        """,
        (user_id, protocol_id),
    )
    baseline_row = cursor.fetchone()

    baseline = None
    if baseline_row:
        baseline = {
            "baseline_date": baseline_row[0].isoformat() if baseline_row[0] else None,
            "protocol_id": protocol_id,
            "rmssd_avg": baseline_row[1],
            "rmssd_7d": baseline_row[2],
            "rmssd_14d": baseline_row[3],
            "rmssd_30d": baseline_row[4],
            "resting_hr": baseline_row[5],
            "resting_hr_7d": baseline_row[6],
            "spo2_avg": baseline_row[7],
            "spo2_min": baseline_row[8],
            "sessions_count_7d": baseline_row[9],
            "sessions_count_14d": baseline_row[10],
            "sessions_count_30d": baseline_row[11],
            "data_quality_score": baseline_row[12],
            "status": baseline_row[13],
            "baseline": baseline_row[14] or {},
        }

    cursor.execute(
        """
        SELECT
            session_id,
            phase,
            window_start,
            window_end,
            avg_hr,
            avg_spo2,
            min_spo2,
            rmssd,
            status,
            data_quality_score,
            features_json,
            created_at
        FROM session_features
        WHERE user_id = %s
          AND protocol_id = %s
          AND session_id NOT LIKE 'PIPELINE_VALIDATION_%%'
        ORDER BY COALESCE(window_start, created_at) DESC, id DESC
        LIMIT %s
        """,
        (
            user_id,
            protocol_id,
            limit,
        ),
    )

    sessions = [
        {
            "session_id": row[0],
            "phase": row[1],
            "window_start": row[2].isoformat() if row[2] else None,
            "window_end": row[3].isoformat() if row[3] else None,
            "avg_hr": row[4],
            "avg_spo2": row[5],
            "min_spo2": row[6],
            "rmssd": row[7],
            "status": row[8],
            "data_quality_score": row[9],
            "features": row[10] or {},
            "created_at": row[11].isoformat() if row[11] else None,
        }
        for row in cursor.fetchall()
    ]

    latest = sessions[0] if sessions else None
    baseline_session_count = int(
        (baseline or {}).get("sessions_count_30d") or 0
    )
    baseline_quality = (baseline or {}).get("data_quality_score")

    if (
        baseline_session_count >= 14
        and (
            baseline_quality is None
            or float(baseline_quality) >= 70
        )
    ):
        baseline_confidence = "ready"
    elif baseline_session_count >= 5:
        baseline_confidence = "early"
    else:
        baseline_confidence = "collecting"

    return {
        "user_id": user_id,
        "protocol_id": protocol_id,
        "wellness_status": (
            latest.get("status")
            if latest
            else (baseline or {}).get("status", "data_quality_warning")
        ),
        "baseline": baseline,
        "baseline_confidence": baseline_confidence,
        "unique_sessions_30d": baseline_session_count,
        "latest_session": latest,
        "recent_sessions": sessions,
        "records": len(sessions),
    }
