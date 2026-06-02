# migrations/update_sessions_table.py

import sqlite3

DB_PATH = "data/database.db"

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# ==========================================
# GET CURRENT COLUMNS
# ==========================================

c.execute("PRAGMA table_info(sessions)")
existing = [x[1] for x in c.fetchall()]

required_columns = {

    "mode": "TEXT",

    "started_at": "TEXT",
    "ended_at": "TEXT",

    "status": "TEXT",

    "anomaly_count": "INTEGER DEFAULT 0",

    "ai_score": "REAL",
    "oai_mean": "REAL",

    "summary": "TEXT",

    "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
}

# ==========================================
# AUTO MIGRATION
# ==========================================

for col, col_type in required_columns.items():

    if col not in existing:

        sql = f"""
        ALTER TABLE sessions
        ADD COLUMN {col} {col_type}
        """

        c.execute(sql)

        print(f"✅ Added column: {col}")

conn.commit()
conn.close()

print("✅ sessions table migration complete")