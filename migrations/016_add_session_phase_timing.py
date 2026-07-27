from database_postgres import db


def upgrade() -> None:
    connection = db()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            UPDATE protocols
            SET
                planned_duration_min = 120,
                compression_time_min = 15,
                exposure_time_min = 90,
                decompression_time_min = 15,
                updated_at = CURRENT_TIMESTAMP
            WHERE code = 'WELLNESS_1_5'
            """
        )

        cursor.execute(
            """
            ALTER TABLE full_sessions
                ADD COLUMN IF NOT EXISTS compression_time_min INTEGER,
                ADD COLUMN IF NOT EXISTS exposure_time_min INTEGER,
                ADD COLUMN IF NOT EXISTS decompression_time_min INTEGER,
                ADD COLUMN IF NOT EXISTS total_duration_min INTEGER
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
