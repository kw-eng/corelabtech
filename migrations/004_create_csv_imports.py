from database_postgres import db


def upgrade() -> None:
    con = db()
    cur = con.cursor()

    try:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS csv_imports (
                id BIGSERIAL PRIMARY KEY,
                session_id VARCHAR(255) NOT NULL,
                user_id VARCHAR(255),
                filename VARCHAR(255) NOT NULL,
                file_hash VARCHAR(64) NOT NULL,
                records_parsed INTEGER NOT NULL DEFAULT 0,
                records_saved INTEGER NOT NULL DEFAULT 0,
                records_rejected INTEGER NOT NULL DEFAULT 0,
                device VARCHAR(100) NOT NULL DEFAULT 'Checkme O2',
                parser_version VARCHAR(50) NOT NULL DEFAULT 'csv-v1',
                status VARCHAR(30) NOT NULL DEFAULT 'processing',
                error_message TEXT,
                first_timestamp TIMESTAMP,
                last_timestamp TIMESTAMP,
                imported_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_csv_import_session_hash
                    UNIQUE(session_id, file_hash)
            )
            """
        )

        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_csv_imports_session_id
            ON csv_imports(session_id)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_csv_imports_user_id
            ON csv_imports(user_id)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_csv_imports_status
            ON csv_imports(status)
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
