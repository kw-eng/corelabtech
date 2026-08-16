"""Create additive, policy-versioned storage for Personal Baseline results."""

from database_postgres import db


def upgrade() -> None:
    connection = db()
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS personal_baselines (
                id BIGSERIAL PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                protocol_id BIGINT REFERENCES protocols(protocol_id),
                baseline_date DATE NOT NULL,
                metric VARCHAR(80) NOT NULL,
                metric_unit VARCHAR(24) NOT NULL,
                status VARCHAR(40) NOT NULL,
                baseline_value DOUBLE PRECISION,
                baseline_center DOUBLE PRECISION,
                baseline_lower_bound DOUBLE PRECISION,
                baseline_upper_bound DOUBLE PRECISION,
                eligible_observation_count INTEGER NOT NULL DEFAULT 0,
                candidate_observation_count INTEGER NOT NULL DEFAULT 0,
                rejected_observation_count INTEGER NOT NULL DEFAULT 0,
                window_days INTEGER NOT NULL,
                baseline_policy_version VARCHAR(80) NOT NULL,
                calculated_at TIMESTAMPTZ NOT NULL,
                lineage_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                baseline_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_personal_baselines_versioned
                    UNIQUE (user_id, protocol_id, baseline_date, metric, baseline_policy_version)
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_personal_baselines_user_protocol_metric_date
            ON personal_baselines(user_id, protocol_id, metric, baseline_date DESC)
            """
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()
