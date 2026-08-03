"""Persist non-identifying LLM operational outcomes for monitoring."""

from database_postgres import db


def upgrade() -> None:
    connection = db()
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS llm_observability_events (
                id BIGSERIAL PRIMARY KEY,
                feature VARCHAR(80) NOT NULL,
                status VARCHAR(80) NOT NULL,
                provider VARCHAR(80),
                model VARCHAR(160),
                latency_ms INTEGER,
                input_tokens INTEGER,
                output_tokens INTEGER,
                total_tokens INTEGER,
                error_type VARCHAR(160),
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_llm_observability_events_created
            ON llm_observability_events(created_at DESC)
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_llm_observability_events_feature_status
            ON llm_observability_events(feature, status, created_at DESC)
            """
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


if __name__ == "__main__":
    upgrade()
