"""Classify recovery follow-ups without changing historical measurements."""

from database_postgres import db


def upgrade() -> None:
    connection = db()
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            ALTER TABLE recovery_follow_ups
            ADD COLUMN IF NOT EXISTS follow_up_window VARCHAR(20)
            NOT NULL DEFAULT 'legacy'
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_recovery_follow_ups_session_window_time
            ON recovery_follow_ups(session_id, follow_up_window, recorded_at DESC)
            """
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()
