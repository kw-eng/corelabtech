from database_postgres import db


def upgrade() -> None:
    con = db()
    cur = con.cursor()

    try:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_results (
                ai_result_id BIGSERIAL PRIMARY KEY,
                merge_id BIGINT NOT NULL,
                session_id VARCHAR(255) NOT NULL,
                user_id VARCHAR(255),
                model_name VARCHAR(100),
                model_version VARCHAR(50),
                overall_score REAL,
                recovery_score REAL,
                stress_score REAL,
                hypoxia_score REAL,
                cardiovascular_score REAL,
                data_quality_score REAL,
                anomaly_detected BOOLEAN DEFAULT FALSE,
                stress_detected BOOLEAN DEFAULT FALSE,
                hypoxia_detected BOOLEAN DEFAULT FALSE,
                arrhythmia_detected BOOLEAN DEFAULT FALSE,
                summary TEXT,
                recommendations TEXT,
                features_json JSONB,
                result_json JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_ai_results_merge
                    FOREIGN KEY (merge_id)
                    REFERENCES merge_jobs(merge_id)
                    ON DELETE CASCADE
            )
            """
        )

        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_ai_results_session
            ON ai_results(session_id)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_ai_results_merge
            ON ai_results(merge_id)
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
