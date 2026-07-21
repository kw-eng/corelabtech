from database_postgres import db


def upgrade() -> None:
    con = db()
    cur = con.cursor()

    try:
        cur.execute(
            """
            ALTER TABLE csv_data
            ADD COLUMN IF NOT EXISTS import_id BIGINT
            """
        )
        cur.execute(
            """
            ALTER TABLE csv_data
            ADD COLUMN IF NOT EXISTS motion INTEGER
            """
        )
        cur.execute(
            """
            ALTER TABLE csv_data
            ADD COLUMN IF NOT EXISTS o2_reminder INTEGER
            """
        )
        cur.execute(
            """
            ALTER TABLE csv_data
            ADD COLUMN IF NOT EXISTS pr_reminder INTEGER
            """
        )

        cur.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'fk_csv_data_import'
                ) THEN
                    ALTER TABLE csv_data
                    ADD CONSTRAINT fk_csv_data_import
                    FOREIGN KEY (import_id)
                    REFERENCES csv_imports(id)
                    ON DELETE CASCADE;
                END IF;
            END $$;
            """
        )

        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_csv_data_import_id
            ON csv_data(import_id)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_csv_data_session_timestamp
            ON csv_data(session_id, timestamp)
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
