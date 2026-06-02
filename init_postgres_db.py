from database_postgres import db


def init_postgres_db():

    con = db()
    c = con.cursor()

    # =========================================================
    # USERS
    # =========================================================

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (

            id SERIAL PRIMARY KEY,

            user_id VARCHAR(64)
            UNIQUE NOT NULL,

            email VARCHAR(255)
            UNIQUE,

            subject_id VARCHAR(100),

            sex VARCHAR(20),

            age INTEGER,

            weight REAL,

            notes TEXT,

            password_hash TEXT,

            role VARCHAR(50)
            DEFAULT 'viewer',

            is_active BOOLEAN
            DEFAULT TRUE,

            created_at TIMESTAMP
            DEFAULT CURRENT_TIMESTAMP,

            updated_at TIMESTAMP
            DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # =========================================================
    # TESTS
    # =========================================================

    c.execute("""
        CREATE TABLE IF NOT EXISTS tests (

            id SERIAL PRIMARY KEY,

            session_id VARCHAR(255),

            user_id VARCHAR(64)
            REFERENCES users(user_id),

            phase VARCHAR(50),

            device VARCHAR(100),

            status VARCHAR(100),

            spo2 REAL,

            pulse REAL,

            hrv REAL,

            pressure REAL,

            pressure_ata REAL,

            ata REAL,

            oxygen_flow_lpm REAL,

            oxygen_percent REAL,

            temperature REAL,

            body_temperature REAL,

            humidity REAL,

            telemetry_json TEXT,

            source VARCHAR(100),

            timestamp TIMESTAMP
            DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # =========================================================
    # FIT DATA
    # =========================================================

    c.execute("""
        CREATE TABLE IF NOT EXISTS fit_data (

            id SERIAL PRIMARY KEY,

            session_id VARCHAR(255),

            user_id VARCHAR(64)
            REFERENCES users(user_id),

            timestamp TEXT,

            heart_rate REAL,

            pulse REAL,

            hr REAL,

            spo2 REAL,

            rr_interval REAL,

            hrv REAL,

            source VARCHAR(100),

            filename TEXT,

            raw_json TEXT,

            uploaded_at TIMESTAMP
            DEFAULT CURRENT_TIMESTAMP,

            created_at TIMESTAMP
            DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # =========================================================
    # CSV DATA
    # =========================================================

    c.execute("""
        CREATE TABLE IF NOT EXISTS csv_data (

            id SERIAL PRIMARY KEY,

            session_id VARCHAR(255),

            user_id VARCHAR(64)
            REFERENCES users(user_id),

            timestamp TEXT,

            pulse REAL,

            heart_rate REAL,

            spo2 REAL,

            source VARCHAR(100),

            filename TEXT,

            raw_json TEXT,

            uploaded_at TIMESTAMP
            DEFAULT CURRENT_TIMESTAMP,

            created_at TIMESTAMP
            DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # =========================================================
    # FULL SESSIONS
    # =========================================================

    c.execute("""
        CREATE TABLE IF NOT EXISTS full_sessions (

            id SERIAL PRIMARY KEY,

            session_id VARCHAR(255)
            UNIQUE NOT NULL,

            user_id VARCHAR(64)
            REFERENCES users(user_id),

            session_status VARCHAR(50)
            DEFAULT 'created',

            pre_json TEXT,

            during_json TEXT,

            post_json TEXT,

            ai_score REAL,

            risk_level VARCHAR(50),

            anomaly BOOLEAN
            DEFAULT FALSE,

            summary TEXT,

            completed INTEGER
            DEFAULT 0,

            created_at TIMESTAMP
            DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # =========================================================
    # INDEXES
    # =========================================================

    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_tests_session_id
        ON tests(session_id)
    """)

    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_tests_user_id
        ON tests(user_id)
    """)

    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_fit_session_id
        ON fit_data(session_id)
    """)

    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_fit_user_id
        ON fit_data(user_id)
    """)

    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_csv_session_id
        ON csv_data(session_id)
    """)

    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_csv_user_id
        ON csv_data(user_id)
    """)

    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_full_sessions_user_id
        ON full_sessions(user_id)
    """)

    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_full_sessions_status
        ON full_sessions(session_status)
    """)

    # =========================================================
    # COMMIT
    # =========================================================

    con.commit()

    c.close()

    con.close()

    print("PostgreSQL database initialized successfully.")


if __name__ == "__main__":
    init_postgres_db()