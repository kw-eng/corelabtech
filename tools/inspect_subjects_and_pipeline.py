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
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'users'
            ORDER BY ordinal_position
            """
        )
        columns = [row[0] for row in cur.fetchall()]
        print("USERS_COLUMNS|" + "|".join(columns))

        cur.execute(
            """
            SELECT *
            FROM users
            ORDER BY created_at DESC NULLS LAST, id DESC
            """
        )
        rows = cur.fetchall()
        print(f"USERS_COUNT|{len(rows)}")
        for row in rows:
            print("USER|" + "|".join(str(value) for value in row))

        cur.execute(
            """
            SELECT
                u.user_id,
                u.role,
                u.subject_id,
                u.created_at,
                COUNT(DISTINCT fs.session_id) AS full_sessions,
                COUNT(DISTINCT fi.id) AS fit_imports,
                COUNT(DISTINCT ci.id) AS csv_imports
            FROM users u
            LEFT JOIN full_sessions fs ON fs.user_id = u.user_id
            LEFT JOIN fit_imports fi ON fi.user_id = u.user_id
            LEFT JOIN csv_imports ci ON ci.user_id = u.user_id
            GROUP BY u.user_id, u.role, u.subject_id, u.created_at
            ORDER BY u.created_at DESC NULLS LAST, u.user_id
            """
        )
        print("SUBJECT_SUMMARY")
        for row in cur.fetchall():
            print("SUBJECT|" + "|".join(str(value) for value in row))
    finally:
        cur.close()
        con.close()


if __name__ == "__main__":
    main()
