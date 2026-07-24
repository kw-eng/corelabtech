from database_postgres import db


def upgrade() -> None:
    con = db()
    cur = con.cursor()

    try:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS hrv_imports (
                id BIGSERIAL PRIMARY KEY,
                session_id VARCHAR(255) NOT NULL,
                user_id VARCHAR(255),
                source VARCHAR(50) NOT NULL,
                filename VARCHAR(255) NOT NULL,
                file_hash VARCHAR(64) NOT NULL,
                device_name VARCHAR(120),
                activity_type VARCHAR(120),
                started_at TIMESTAMP,
                duration_seconds INTEGER,
                rr_samples INTEGER NOT NULL DEFAULT 0,
                artifact_samples INTEGER NOT NULL DEFAULT 0,
                parser_version VARCHAR(50) NOT NULL DEFAULT 'hrv-v1',
                status VARCHAR(30) NOT NULL DEFAULT 'processing',
                error_message TEXT,
                imported_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_hrv_import_session_hash
                    UNIQUE(session_id, file_hash)
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS hrv_intervals (
                id BIGSERIAL PRIMARY KEY,
                import_id BIGINT NOT NULL,
                session_id VARCHAR(255) NOT NULL,
                user_id VARCHAR(255),
                timestamp TIMESTAMP,
                rr_interval_ms DOUBLE PRECISION NOT NULL,
                quality_flag VARCHAR(50),
                source VARCHAR(50) NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_hrv_intervals_import
                    FOREIGN KEY (import_id)
                    REFERENCES hrv_imports(id)
                    ON DELETE CASCADE
            )
            """
        )

        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_hrv_imports_session
            ON hrv_imports(session_id)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_hrv_imports_user
            ON hrv_imports(user_id)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_hrv_imports_status
            ON hrv_imports(status)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_hrv_intervals_import
            ON hrv_intervals(import_id)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_hrv_intervals_session_timestamp
            ON hrv_intervals(session_id, timestamp)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_hrv_intervals_user_timestamp
            ON hrv_intervals(user_id, timestamp)
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
