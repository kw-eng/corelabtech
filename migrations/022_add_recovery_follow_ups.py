"""Store optional post-session recovery follow-ups separately from raw telemetry."""

from database_postgres import db


def upgrade() -> None:
    connection = db()
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS recovery_follow_ups (
                id BIGSERIAL PRIMARY KEY,
                session_id VARCHAR(255) NOT NULL,
                user_id VARCHAR(255) NOT NULL,
                recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                energy_level VARCHAR(30),
                fatigue_level VARCHAR(30),
                sleep_quality VARCHAR(30),
                discomfort VARCHAR(30),
                heart_rate_bpm DOUBLE PRECISION,
                spo2 DOUBLE PRECISION,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_recovery_follow_ups_session_time
            ON recovery_follow_ups(session_id, recorded_at DESC)
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
