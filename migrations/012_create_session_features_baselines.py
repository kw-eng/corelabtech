from database_postgres import db


def upgrade() -> None:
    con = db()
    cur = con.cursor()

    try:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS session_features (
                id BIGSERIAL PRIMARY KEY,
                session_id VARCHAR(255) NOT NULL,
                user_id VARCHAR(255),
                phase VARCHAR(50) NOT NULL,
                window_start TIMESTAMP,
                window_end TIMESTAMP,
                avg_hr DOUBLE PRECISION,
                min_hr DOUBLE PRECISION,
                max_hr DOUBLE PRECISION,
                avg_spo2 DOUBLE PRECISION,
                min_spo2 DOUBLE PRECISION,
                max_spo2 DOUBLE PRECISION,
                rmssd DOUBLE PRECISION,
                sdnn DOUBLE PRECISION,
                pnn50 DOUBLE PRECISION,
                rr_count INTEGER NOT NULL DEFAULT 0,
                artifact_ratio DOUBLE PRECISION,
                hr_response DOUBLE PRECISION,
                spo2_drop DOUBLE PRECISION,
                recovery_delta DOUBLE PRECISION,
                deviation_from_baseline DOUBLE PRECISION,
                status VARCHAR(50),
                data_quality_score DOUBLE PRECISION,
                features_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_session_features_phase_window
                    UNIQUE(session_id, phase, window_start, window_end)
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_baselines (
                id BIGSERIAL PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                baseline_date DATE NOT NULL,
                rmssd_avg DOUBLE PRECISION,
                rmssd_7d DOUBLE PRECISION,
                rmssd_14d DOUBLE PRECISION,
                rmssd_30d DOUBLE PRECISION,
                resting_hr DOUBLE PRECISION,
                resting_hr_7d DOUBLE PRECISION,
                spo2_avg DOUBLE PRECISION,
                spo2_min DOUBLE PRECISION,
                sessions_count_7d INTEGER NOT NULL DEFAULT 0,
                sessions_count_14d INTEGER NOT NULL DEFAULT 0,
                sessions_count_30d INTEGER NOT NULL DEFAULT 0,
                data_quality_score DOUBLE PRECISION,
                status VARCHAR(50),
                baseline_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_daily_baselines_user_date
                    UNIQUE(user_id, baseline_date)
            )
            """
        )

        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_session_features_session
            ON session_features(session_id)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_session_features_user_phase
            ON session_features(user_id, phase)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_session_features_window
            ON session_features(window_start, window_end)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_daily_baselines_user_date
            ON daily_baselines(user_id, baseline_date)
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
