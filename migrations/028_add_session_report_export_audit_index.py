"""Index the audit lookup used by the Research session-list export state."""

from database_postgres import db


def upgrade() -> None:
    connection = db()
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_audit_log_session_report_exports
            ON audit_log (entity_id, created_at DESC)
            WHERE action = 'report.export'
              AND entity_type = 'session'
              AND outcome = 'success'
            """
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()
