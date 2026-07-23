from database_postgres import db


def upgrade() -> None:
    con = db()
    cur = con.cursor()

    try:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS merge_jobs (
                merge_id BIGSERIAL PRIMARY KEY,
                session_id VARCHAR(255) NOT NULL,
                user_id VARCHAR(255),
                fit_import_id BIGINT,
                csv_import_id BIGINT,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                finished_at TIMESTAMP,
                fit_records INTEGER DEFAULT 0,
                csv_records INTEGER DEFAULT 0,
                merged_records INTEGER DEFAULT 0,
                algorithm VARCHAR(100) DEFAULT 'nearest_timestamp',
                tolerance_ms INTEGER DEFAULT 2500,
                status VARCHAR(30) DEFAULT 'RUNNING',
                notes TEXT,
                CONSTRAINT fk_merge_jobs_fit_import
                    FOREIGN KEY (fit_import_id)
                    REFERENCES fit_imports(id),
                CONSTRAINT fk_merge_jobs_csv_import
                    FOREIGN KEY (csv_import_id)
                    REFERENCES csv_imports(id)
            )
            """
        )

        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_merge_jobs_session
            ON merge_jobs(session_id)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_merge_jobs_status
            ON merge_jobs(status)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_merge_jobs_finished
            ON merge_jobs(finished_at)
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
