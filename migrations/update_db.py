import sqlite3

DB_PATH = "data/database.db"


# =========================
# CHECK COLUMN
# =========================
def column_exists(cursor, table, column):
    cursor.execute(f"PRAGMA table_info({table})")
    return column in [col[1] for col in cursor.fetchall()]


# =========================
# ADD COLUMN SAFE
# =========================
def add_column(cursor, table, column_def):
    col_name = column_def.split()[0]

    try:
        if not column_exists(cursor, table, col_name):
            print(f"[ADD] {col_name}")
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column_def}")
        else:
            print(f"[OK] {col_name} exists")
    except Exception as e:
        print(f"[ERROR] {col_name}: {e}")


# =========================
# MIGRATION
# =========================
def migrate():

    print("Starting migration...\n")

    con = sqlite3.connect(DB_PATH)
    c = con.cursor()

    columns = []
    # 🔥 CORE
    "user_id TEXT",
    "session_id TEXT",
    # 🔥 LOGIKA
    "phase TEXT",
    "device TEXT",
    "status TEXT",
    # 🔥 PHYSIOLOGY
    "spo2 REAL",
    "pulse REAL",
    "hrv REAL",
    # 🔥 PRESSURE
    "pressure_kpa REAL",
    "pressure_ata REAL",
    # 🔥 OXYGEN
    "chamber_oxygen_percent REAL",
    "oxygen_flow_lpm REAL",
    "oxygen_mask_percent REAL",
    # 🔥 TEMPERATURE
    "body_temperature REAL",
    "chamber_temperature REAL",
    # 🔥 ENVIRONMENT
    "humidity REAL",
    # 🔥 TIME SERIES (KLUCZOWE)
    "timestamp TEXT",
    for col in columns:
        add_column(c, "tests", col)

    # =========================
    # INDEXES (PRO)
    # =========================
    print("\nCreating indexes...")
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_session ON tests(session_id)",
        "CREATE INDEX IF NOT EXISTS idx_user ON tests(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_phase ON tests(phase)",
        "CREATE INDEX IF NOT EXISTS idx_timestamp ON tests(timestamp)",
    ]
    for idx in indexes:
        try:
            c.execute(idx)
            print(f"[INDEX OK]")
        except Exception as e:
            print(f"[INDEX ERROR]: {e}")
    con.commit()
    con.close()

    print("\nMigration DONE 🚀")

    # =========================
    # RUN
    # =========================
    if __name__ == "__main__":
        migrate()
