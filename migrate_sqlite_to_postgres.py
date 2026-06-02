import sqlite3
from database_postgres import db as pg_db


SQLITE_PATH = "data/database.db"


def sqlite_rows(table):

    con = sqlite3.connect(SQLITE_PATH)
    con.row_factory = sqlite3.Row
    c = con.cursor()

    c.execute(f"SELECT * FROM {table}")
    rows = c.fetchall()

    con.close()

    return [dict(row) for row in rows]


def migrate_users(pg):

    rows = sqlite_rows("users")
    c = pg.cursor()

    print(f"Migrating users: {len(rows)} rows")

    for r in rows:

        c.execute("""
            INSERT INTO users (
                user_id,
                email,
                subject_id,
                sex,
                age,
                weight,
                notes,
                password_hash,
                role,
                is_active
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO NOTHING
        """, (
            r.get("user_id") or str(r.get("id")),
            r.get("email"),
            r.get("subject_id"),
            r.get("sex"),
            r.get("age"),
            r.get("weight"),
            r.get("notes"),
            r.get("password_hash"),
            r.get("role") or "viewer",
            True if r.get("is_active") is None else bool(r.get("is_active")),
        ))

    pg.commit()


def ensure_missing_users(pg):

    c = pg.cursor()

    tables = [
        "tests",
        "fit_data",
        "csv_data",
        "full_sessions"
    ]

    user_ids = set()

    for table in tables:

        rows = sqlite_rows(table)

        for r in rows:

            user_id = r.get("user_id")

            if user_id:
                user_ids.add(str(user_id))

    print(f"Ensuring missing users: {len(user_ids)} user_ids found")

    for user_id in user_ids:

        c.execute("""
            INSERT INTO users (
                user_id,
                subject_id,
                role,
                is_active,
                notes
            )
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO NOTHING
        """, (
            user_id,
            user_id,
            "viewer",
            True,
            "Auto-created during SQLite migration"
        ))

    pg.commit()


def migrate_tests(pg):

    rows = sqlite_rows("tests")
    c = pg.cursor()

    print(f"Migrating tests: {len(rows)} rows")

    for r in rows:

        c.execute("""
            INSERT INTO tests (
                session_id,
                user_id,
                phase,
                device,
                status,
                spo2,
                pulse,
                hrv,
                pressure,
                pressure_ata,
                ata,
                oxygen_flow_lpm,
                oxygen_percent,
                temperature,
                body_temperature,
                humidity,
                telemetry_json,
                source
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            r.get("session_id"),
            r.get("user_id"),
            r.get("phase"),
            r.get("device"),
            r.get("status"),
            r.get("spo2"),
            r.get("pulse"),
            r.get("hrv"),
            r.get("pressure"),
            r.get("pressure_ata"),
            r.get("ata"),
            r.get("oxygen_flow_lpm"),
            r.get("oxygen_percent"),
            r.get("temperature"),
            r.get("body_temperature"),
            r.get("humidity"),
            r.get("telemetry_json"),
            r.get("source"),
        ))

    pg.commit()


def migrate_fit_data(pg):

    rows = sqlite_rows("fit_data")
    c = pg.cursor()

    print(f"Migrating fit_data: {len(rows)} rows")

    for r in rows:

        c.execute("""
            INSERT INTO fit_data (
                session_id,
                user_id,
                timestamp,
                heart_rate,
                pulse,
                hr,
                spo2,
                rr_interval,
                hrv,
                source,
                filename,
                raw_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            r.get("session_id"),
            r.get("user_id"),
            r.get("timestamp"),
            r.get("heart_rate"),
            r.get("pulse"),
            r.get("hr"),
            r.get("spo2"),
            r.get("rr_interval"),
            r.get("hrv"),
            r.get("source"),
            r.get("filename"),
            r.get("raw_json"),
        ))

    pg.commit()


def migrate_csv_data(pg):

    rows = sqlite_rows("csv_data")
    c = pg.cursor()

    print(f"Migrating csv_data: {len(rows)} rows")

    for r in rows:

        c.execute("""
            INSERT INTO csv_data (
                session_id,
                user_id,
                timestamp,
                pulse,
                heart_rate,
                spo2,
                source,
                filename,
                raw_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            r.get("session_id"),
            r.get("user_id"),
            r.get("timestamp"),
            r.get("pulse"),
            r.get("heart_rate"),
            r.get("spo2"),
            r.get("source"),
            r.get("filename"),
            r.get("raw_json"),
        ))

    pg.commit()


def migrate_full_sessions(pg):

    rows = sqlite_rows("full_sessions")
    c = pg.cursor()

    print(f"Migrating full_sessions: {len(rows)} rows")

    for r in rows:

        c.execute("""
            INSERT INTO full_sessions (
                session_id,
                user_id,
                session_status,
                pre_json,
                during_json,
                post_json,
                ai_score,
                risk_level,
                anomaly,
                summary,
                completed
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (session_id) DO NOTHING
        """, (
            r.get("session_id"),
            r.get("user_id"),
            r.get("session_status") or "completed",
            r.get("pre_json"),
            r.get("during_json"),
            r.get("post_json"),
            r.get("ai_score"),
            r.get("risk_level"),
            bool(r.get("anomaly")) if r.get("anomaly") is not None else False,
            r.get("summary"),
            r.get("completed") or 0,
        ))

    pg.commit()


def migrate_all():

    pg = pg_db()

    try:

        migrate_users(pg)

        ensure_missing_users(pg)

        migrate_tests(pg)

        migrate_fit_data(pg)

        migrate_csv_data(pg)

        migrate_full_sessions(pg)

        print("-" * 40)
        print("SQLite to PostgreSQL migration completed.")

    finally:

        pg.close()


if __name__ == "__main__":
    migrate_all()