# =========================================
# init_db.py
# FINAL HBOT AI DATABASE
# RAW DATA + AI PIPELINE READY
# =========================================

import sqlite3
import os

# =========================================
# CREATE DATA DIRECTORIES
# =========================================

os.makedirs("data", exist_ok=True)
os.makedirs("data/uploads", exist_ok=True)
os.makedirs("data/uploads/fit", exist_ok=True)
os.makedirs("data/uploads/csv", exist_ok=True)
os.makedirs("data/uploads/temp", exist_ok=True)

DB_PATH = "data/database.db"

# =========================================
# CONNECT
# =========================================

con = sqlite3.connect(DB_PATH)
c = con.cursor()

# =========================================
# USERS
# =========================================

c.execute("""
CREATE TABLE IF NOT EXISTS users (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    user_id TEXT UNIQUE,

    subject_id TEXT UNIQUE,

    sex TEXT,

    age INTEGER,

    weight REAL,

    notes TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

)
""")

# =========================================
# TESTS
# phase autosave / PRE-DURING-POST markers
# =========================================

c.execute("""
CREATE TABLE IF NOT EXISTS tests (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    session_id TEXT,

    user_id TEXT,

    phase TEXT,

    mode TEXT,

    device TEXT,

    status TEXT,

    timestamp TEXT,

    date TEXT,

    spo2 REAL,

    pulse REAL,

    heart_rate REAL,

    hrv REAL,

    rr_interval REAL,

    pressure REAL,

    pressure_kpa REAL,

    pressure_ata REAL,

    ata REAL,

    oxygen_flow_lpm REAL,

    oxygen_percent REAL,

    oxygen_mask_percent REAL,

    chamber_oxygen_percent REAL,

    temperature REAL,

    chamber_temperature REAL,

    body_temperature REAL,

    humidity REAL,

    anomaly INTEGER DEFAULT 0,

    anomaly_label TEXT,

    ai_score REAL,

    ai_confidence REAL,

    oai REAL,

    source TEXT,

    telemetry_json TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

)
""")

# =========================================
# FULL SESSIONS
# final research package: PRE + DURING timeline + POST
# =========================================

c.execute("""
CREATE TABLE IF NOT EXISTS full_sessions (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    session_id TEXT UNIQUE,

    user_id TEXT,

    pre_json TEXT,

    during_json TEXT,

    post_json TEXT,

    summary TEXT,

    ai_score REAL,

    anomaly_count INTEGER DEFAULT 0,

    completed INTEGER DEFAULT 0,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

)
""")

# =========================================
# SESSIONS
# UI / workflow state
# =========================================

c.execute("""
CREATE TABLE IF NOT EXISTS sessions (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    session_id TEXT UNIQUE,

    user_id TEXT,

    mode TEXT,

    started_at TEXT,

    ended_at TEXT,

    status TEXT,

    current_phase TEXT,

    progress INTEGER DEFAULT 0,

    anomaly_count INTEGER DEFAULT 0,

    ai_score REAL,

    oai_mean REAL,

    summary TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

)
""")

# =========================================
# TELEMETRY
# realtime monitor
# =========================================

c.execute("""
CREATE TABLE IF NOT EXISTS telemetry (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    session_id TEXT,

    timestamp TEXT,

    spo2 REAL,

    pulse REAL,

    heart_rate REAL,

    hrv REAL,

    rr_interval REAL,

    pressure REAL,

    pressure_kpa REAL,

    pressure_ata REAL,

    ata REAL,

    oxygen_flow_lpm REAL,

    oxygen_percent REAL,

    oxygen_mask_percent REAL,

    temperature REAL,

    chamber_temperature REAL,

    body_temperature REAL,

    humidity REAL,

    ai_score REAL,

    anomaly INTEGER DEFAULT 0,

    alert TEXT,

    source TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

)
""")

# =========================================
# FIT RAW DATA
# Garmin/FIT timeline
# =========================================

c.execute("""
CREATE TABLE IF NOT EXISTS fit_data (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    session_id TEXT,

    user_id TEXT,

    timestamp TEXT,

    heart_rate REAL,

    pulse REAL,

    hr REAL,

    spo2 REAL,

    hrv REAL,

    rr_interval REAL,

    source TEXT,

    raw_json TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

)
""")

# =========================================
# CSV RAW DATA
# External sensor / pulseox / manual timeline
# =========================================

c.execute("""
CREATE TABLE IF NOT EXISTS csv_data (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    session_id TEXT,

    user_id TEXT,

    timestamp TEXT,

    pulse REAL,

    heart_rate REAL,

    spo2 REAL,

    source TEXT,

    raw_json TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

)
""")

# =========================================
# AI LOGS
# =========================================

c.execute("""
CREATE TABLE IF NOT EXISTS ai_logs (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    session_id TEXT,

    phase TEXT,

    input_json TEXT,

    output_json TEXT,

    model TEXT,

    ai_score REAL,

    anomaly INTEGER DEFAULT 0,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

)
""")

# =========================================
# AI ANOMALIES
# =========================================

c.execute("""
CREATE TABLE IF NOT EXISTS ai_anomalies (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    session_id TEXT,

    timestamp TEXT,

    anomaly_type TEXT,

    severity REAL,

    spo2 REAL,

    pulse REAL,

    hrv REAL,

    pressure_ata REAL,

    ai_score REAL,

    notes TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

)
""")

# =========================================
# PLAYWRIGHT RUNS
# =========================================

c.execute("""
CREATE TABLE IF NOT EXISTS playwright_runs (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    timestamp TEXT,

    status TEXT,

    returncode INTEGER,

    stdout TEXT,

    stderr TEXT,

    retries INTEGER DEFAULT 0,

    flaky INTEGER DEFAULT 0,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

)
""")

# =========================================
# WEBSOCKET EVENTS
# =========================================

c.execute("""
CREATE TABLE IF NOT EXISTS websocket_events (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    session_id TEXT,

    event_type TEXT,

    payload_json TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

)
""")

# =========================================
# INDEXES
# PERFORMANCE
# =========================================

c.execute("""
CREATE INDEX IF NOT EXISTS idx_users_user_id
ON users(user_id)
""")

c.execute("""
CREATE INDEX IF NOT EXISTS idx_tests_session
ON tests(session_id)
""")

c.execute("""
CREATE INDEX IF NOT EXISTS idx_tests_phase
ON tests(phase)
""")

c.execute("""
CREATE INDEX IF NOT EXISTS idx_fit_session
ON fit_data(session_id)
""")

c.execute("""
CREATE INDEX IF NOT EXISTS idx_csv_session
ON csv_data(session_id)
""")

c.execute("""
CREATE INDEX IF NOT EXISTS idx_full_sessions_session
ON full_sessions(session_id)
""")

c.execute("""
CREATE INDEX IF NOT EXISTS idx_telemetry_session
ON telemetry(session_id)
""")

c.execute("""
CREATE INDEX IF NOT EXISTS idx_ai_session
ON ai_logs(session_id)
""")

c.execute("""
CREATE INDEX IF NOT EXISTS idx_ai_anomalies_session
ON ai_anomalies(session_id)
""")

# =========================================
# COMMIT
# =========================================

con.commit()
con.close()

# =========================================
# DONE
# =========================================

print("[OK] FINAL HBOT AI DATABASE INITIALIZED")
print("[OK] SQLite path:", DB_PATH)