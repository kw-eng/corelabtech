"""Persistence boundary for evidence-governed Personal Baselines."""

from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any

from services.personal_baseline import METRIC_DEFINITIONS, calculate_personal_baseline


LOGGER = logging.getLogger(__name__)


def load_baseline_observations(cursor, *, user_id: str, as_of: date) -> list[dict[str, Any]]:
    """Load a bounded, user-scoped candidate set in one indexed query."""

    cursor.execute(
        """
        SELECT
            session_id, user_id, protocol_id, phase,
            COALESCE(window_start::date, created_at::date),
            target_ata, data_quality_score, features_json
        FROM session_features
        WHERE user_id = %s
          AND session_id NOT LIKE 'PIPELINE_VALIDATION_%%'
          AND COALESCE(window_start::date, created_at::date) <= %s
          AND COALESCE(window_start::date, created_at::date) >= %s::date - INTERVAL '29 days'
        ORDER BY COALESCE(window_start, created_at), id
        """,
        (user_id, as_of, as_of),
    )
    return [
        {
            "session_id": row[0], "user_id": row[1], "protocol_id": row[2],
            "phase": row[3], "observed_at": row[4], "target_ata": row[5],
            "data_quality_score": row[6], "features": row[7] or {},
        }
        for row in cursor.fetchall()
    ]


def refresh_personal_baselines(cursor, *, user_id: str, protocol_id: int, target_ata: float | None, baseline_date: date) -> list[dict[str, Any]]:
    """Materialize v1 baseline results after a session analysis completes."""

    observations = load_baseline_observations(cursor, user_id=user_id, as_of=baseline_date)
    results = [
        calculate_personal_baseline(
            user_id=user_id, metric=metric, observations=observations,
            protocol_id=protocol_id, target_ata=target_ata, as_of=baseline_date,
        )
        for metric in METRIC_DEFINITIONS
    ]
    for baseline in results:
        save_personal_baseline(cursor, baseline=baseline, baseline_date=baseline_date)
        LOGGER.info(
            "personal_baseline_calculated policy=%s metric=%s status=%s eligible=%s rejected=%s",
            baseline["baseline_policy_version"], baseline["metric"], baseline["status"],
            baseline["eligible_observation_count"], baseline["rejected_observation_count"],
        )
    return results


def save_personal_baseline(cursor, *, baseline: dict[str, Any], baseline_date: date) -> None:
    """Store a policy-versioned materialization without changing legacy rows."""

    cursor.execute(
        """
        INSERT INTO personal_baselines (
            user_id, protocol_id, baseline_date, metric, metric_unit, status,
            baseline_value, baseline_center, baseline_lower_bound, baseline_upper_bound,
            eligible_observation_count, candidate_observation_count,
            rejected_observation_count, window_days, baseline_policy_version,
            calculated_at, lineage_json, baseline_json
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s::jsonb, %s::jsonb
        )
        ON CONFLICT (user_id, protocol_id, baseline_date, metric, baseline_policy_version)
        DO UPDATE SET
            metric_unit = EXCLUDED.metric_unit, status = EXCLUDED.status,
            baseline_value = EXCLUDED.baseline_value, baseline_center = EXCLUDED.baseline_center,
            baseline_lower_bound = EXCLUDED.baseline_lower_bound,
            baseline_upper_bound = EXCLUDED.baseline_upper_bound,
            eligible_observation_count = EXCLUDED.eligible_observation_count,
            candidate_observation_count = EXCLUDED.candidate_observation_count,
            rejected_observation_count = EXCLUDED.rejected_observation_count,
            window_days = EXCLUDED.window_days, calculated_at = EXCLUDED.calculated_at,
            lineage_json = EXCLUDED.lineage_json, baseline_json = EXCLUDED.baseline_json
        """,
        (
            baseline["user_id"], baseline["protocol_scope"]["protocol_id"], baseline_date,
            baseline["metric"], baseline["metric_unit"], baseline["status"],
            baseline["baseline_value"], baseline["baseline_center"],
            baseline["baseline_lower_bound"], baseline["baseline_upper_bound"],
            baseline["eligible_observation_count"], baseline["candidate_observation_count"],
            baseline["rejected_observation_count"], baseline["window_days"],
            baseline["baseline_policy_version"], baseline["calculated_at"],
            json.dumps({"eligible_session_refs": baseline["eligible_session_refs"], "rejections": baseline["rejections"]}),
            json.dumps(baseline, default=str),
        ),
    )
