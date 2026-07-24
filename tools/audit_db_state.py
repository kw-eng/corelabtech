from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

load_dotenv()
os.environ["DATABASE_URL"] = os.environ["DATABASE_URL"].replace("@db:", "@localhost:")

from database_postgres import db  # noqa: E402


def main() -> None:
    con = db()
    cur = con.cursor()
    try:
        cur.execute(
            """
            SELECT version, filename, applied_at
            FROM schema_migrations
            ORDER BY version
            """
        )
        print("MIGRATIONS")
        for row in cur.fetchall():
            print(row)

        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
            """
        )
        tables = [row[0] for row in cur.fetchall()]
        print("TABLES", tables)

        for table in [
            "users",
            "full_sessions",
            "fit_imports",
            "csv_imports",
            "merge_jobs",
            "merged_data",
            "ai_results",
            "session_features",
            "daily_baselines",
            "hrv_imports",
            "hrv_intervals",
        ]:
            if table not in tables:
                print("MISSING_TABLE", table)
                continue
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            print("COUNT", table, cur.fetchone()[0])

        cur.execute(
            """
            SELECT session_id, user_id, overall_score, data_quality_score,
                   result_json->>'wellness_status',
                   result_json->'quality_warnings',
                   created_at
            FROM ai_results
            ORDER BY created_at DESC, ai_result_id DESC
            LIMIT 5
            """
        )
        print("LATEST_AI")
        for row in cur.fetchall():
            print(row)
    finally:
        cur.close()
        con.close()


if __name__ == "__main__":
    main()
