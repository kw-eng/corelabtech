from database_postgres import db


def upgrade() -> None:
    con = db()
    cur = con.cursor()

    try:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS fit_imports (
                id BIGSERIAL PRIMARY KEY,
                session_id VARCHAR(255) NOT NULL,
                user_id VARCHAR(255),
                filename VARCHAR(255) NOT NULL,
                file_hash VARCHAR(64) NOT NULL,
                file_size BIGINT,
                parser_version VARCHAR(50) NOT NULL DEFAULT 'fit-v1',
                manufacturer VARCHAR(100),
                product VARCHAR(100),
                device_serial VARCHAR(100),
                records_parsed INTEGER NOT NULL DEFAULT 0,
                records_saved INTEGER NOT NULL DEFAULT 0,
                records_rejected INTEGER NOT NULL DEFAULT 0,
                first_timestamp TIMESTAMP,
                last_timestamp TIMESTAMP,
                status VARCHAR(30) NOT NULL DEFAULT 'processing',
                error_message TEXT,
                imported_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_fit_import_session_hash
                    UNIQUE(session_id, file_hash)
            )
            """
        )

        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_fit_import_session
            ON fit_imports(session_id)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_fit_import_user
            ON fit_imports(user_id)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_fit_import_status
            ON fit_imports(status)
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
