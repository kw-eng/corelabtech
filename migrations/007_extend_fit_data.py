from database_postgres import db


def upgrade() -> None:
    con = db()
    cur = con.cursor()

    try:
        cur.execute(
            """
            ALTER TABLE fit_data
            ADD COLUMN IF NOT EXISTS import_id BIGINT
            """
        )

        cur.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'fk_fit_data_import'
                ) THEN
                    ALTER TABLE fit_data
                    ADD CONSTRAINT fk_fit_data_import
                    FOREIGN KEY (import_id)
                    REFERENCES fit_imports(id)
                    ON DELETE CASCADE;
                END IF;
            END $$;
            """
        )

        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_fit_data_import
            ON fit_data(import_id)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_fit_data_session_timestamp
            ON fit_data(session_id, timestamp)
            """
        )

        con.commit()

    except Exception:
        con.rollback()
        raise

    finally:
        cur.close()
        con.close()


if __name__ == "__main__":
    upgrade()
