"""Record the original file format for wearable telemetry imports."""

from database_postgres import db


def upgrade() -> None:
    connection = db()
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            ALTER TABLE fit_imports
            ADD COLUMN IF NOT EXISTS import_type VARCHAR(50)
            NOT NULL DEFAULT 'fit'
            """
        )
        cursor.execute(
            """
            UPDATE fit_imports
            SET import_type = 'fit'
            WHERE import_type IS NULL OR BTRIM(import_type) = ''
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_fit_imports_session_type
            ON fit_imports(session_id, import_type, imported_at DESC)
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
