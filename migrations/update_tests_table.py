# migrations/update_tests_table.py

import sqlite3

DB_PATH = "data/database.db"

# =====================================================
# CHECK COLUMN EXISTS
# =====================================================

def column_exists(cursor, table, column):

    cursor.execute(f"PRAGMA table_info({table})")

    cols = [c[1] for c in cursor.fetchall()]

    return column in cols

# =====================================================
# SAFE ADD COLUMN
# =====================================================

def add_column(cursor, table, definition):

    col_name = definition.split()[0]

    if not column_exists(cursor, table, col_name):

        print(f"✅ Adding column: {col_name}")

        cursor.execute(
            f"ALTER TABLE {table} ADD COLUMN {definition}"
        )

    else:

        print(f"✔ Exists: {col_name}")

# =====================================================
# MAIN MIGRATION
# =====================================================

def migrate():

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    columns = [

        # =================================================
        # SESSION
        # =================================================

        "session_id TEXT",
        "user_id TEXT",

        "mode TEXT",
        "phase TEXT",

        "status TEXT",

        # =================================================
        # TIME
        # =================================================

        "timestamp TEXT",
        "date TEXT",

        # =================================================
        # DEVICE
        # =================================================

        "device TEXT",
        "source TEXT",

        # =================================================
        # PHYSIOLOGY
        # =================================================

        "spo2 REAL",
        "pulse REAL",

        "heart_rate REAL",

        "hrv REAL",
        "rr_interval REAL",

        # =================================================
        # PRESSURE
        # =================================================

        "pressure REAL",
        "pressure_kpa REAL",

        "ata REAL",
        "pressure_ata REAL",

        # =================================================
        # OXYGEN
        # =================================================

        "chamber_oxygen_percent REAL",
        "oxygen_flow_lpm REAL",
        "oxygen_mask_percent REAL",

        # =================================================
        # TEMPERATURE
        # =================================================

        "body_temperature REAL",
        "temperature REAL",
        "chamber_temperature REAL",

        # =================================================
        # ENVIRONMENT
        # =================================================

        "humidity REAL",

        # =================================================
        # AI
        # =================================================

        "anomaly INTEGER DEFAULT 0",

        "ai_score REAL",

        "oai REAL",

        "stress_index REAL",

        # =================================================
        # PIPELINE
        # =================================================

        "hr_smooth REAL",
        "hr_diff REAL",

        "rmssd_60 REAL",
        "sdnn_60 REAL",

        "spo2_std_30 REAL",

        "hr_pulse_gap REAL",

        "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
    ]

    # =====================================================
    # APPLY MIGRATION
    # =====================================================

    for col in columns:

        add_column(c, "tests", col)

    # =====================================================
    # INDEXES
    # =====================================================

    print("\n📌 Creating indexes...\n")

    indexes = [

        ("idx_tests_session", "session_id"),
        ("idx_tests_user", "user_id"),
        ("idx_tests_phase", "phase"),
        ("idx_tests_timestamp", "timestamp"),
        ("idx_tests_mode", "mode")
    ]

    for idx_name, field in indexes:

        c.execute(f"""
        CREATE INDEX IF NOT EXISTS
        {idx_name}
        ON tests({field})
        """)

    conn.commit()
    conn.close()

    print("\n✅ TESTS TABLE MIGRATION COMPLETE")

# =====================================================
# RUN
# =====================================================

if __name__ == "__main__":

    migrate()