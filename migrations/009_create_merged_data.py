from database_postgres import db


def upgrade() -> None:
    con = db()
    cur = con.cursor()

    try:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS merged_data (
                id BIGSERIAL PRIMARY KEY,
                merge_id BIGINT NOT NULL,
                session_id VARCHAR(255) NOT NULL,
                user_id VARCHAR(255),
                timestamp TIMESTAMP NOT NULL,
                phase VARCHAR(50),
                heart_rate DOUBLE PRECISION,
                hrv DOUBLE PRECISION,
                rr_interval DOUBLE PRECISION,
                spo2 DOUBLE PRECISION,
                pulse DOUBLE PRECISION,
                motion INTEGER,
                fit_timestamp TIMESTAMP,
                csv_timestamp TIMESTAMP,
                delta_ms INTEGER,
                synchronized BOOLEAN DEFAULT FALSE,
                status VARCHAR(30),
                is_hypoxia BOOLEAN DEFAULT FALSE,
                is_stress BOOLEAN DEFAULT FALSE,
                is_outlier BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_merged_data_merge
                    FOREIGN KEY (merge_id)
                    REFERENCES merge_jobs(merge_id)
                    ON DELETE CASCADE
            )
            """
        )

        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_merged_data_session
            ON merged_data(session_id)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_merged_data_timestamp
            ON merged_data(timestamp)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_merged_data_merge
            ON merged_data(merge_id)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_merged_data_session_timestamp
            ON merged_data(session_id, timestamp)
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
