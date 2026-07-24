from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

load_dotenv()

if os.getenv("CORELABTECH_FORCE_LOCAL_DB", "false").lower() == "true":
    os.environ["DATABASE_URL"] = os.environ["DATABASE_URL"].replace(
        "@db:",
        "@localhost:",
    )

from database_postgres import db  # noqa: E402
from services.data_ingestion import import_csv_file, import_fit_file  # noqa: E402
from services.data_merge import merge_session_data  # noqa: E402
from services.analysis_service import run_session_analysis  # noqa: E402


FIT_PATH = ROOT / "files" / "fenix8" / "23664778759_ACTIVITY.fit"
CSV_PATH = ROOT / "files" / "checkme" / "Checkme O2 _20260720130928.csv"


def clean_subjects() -> None:
    keep = ["admin", "operator", "researcher_demo", "HBOT", "HBOT_001"]

    con = db()
    cur = con.cursor()
    try:
        cur.execute(
            """
            UPDATE users
            SET is_active = CASE WHEN user_id = ANY(%s) THEN TRUE ELSE FALSE END
            """,
            (keep,),
        )
        con.commit()

        cur.execute(
            """
            SELECT user_id, role, subject_id, is_active
            FROM users
            ORDER BY is_active DESC, user_id
            """
        )
        print("SUBJECTS_AFTER_CLEAN")
        for row in cur.fetchall():
            print("SUBJECT", row[0], row[1], row[2], row[3])
    except Exception:
        con.rollback()
        raise
    finally:
        cur.close()
        con.close()


def ensure_migrations() -> None:
    import run_database_setup

    run_database_setup.run_migrations()


def test_pipeline() -> None:
    session_id = "PIPELINE_VALIDATION_20260724"
    user_id = "HBOT"

    con = db()
    cur = con.cursor()
    try:
        cleanup_session_data(cur, session_id=session_id)
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        cur.close()
        con.close()

    fit_result = import_fit_file(
        path=FIT_PATH,
        filename=FIT_PATH.name,
        session_id=session_id,
        user_id=user_id,
    )
    print("FIT_IMPORT", fit_result.to_dict())

    csv_result = import_csv_file(
        path=CSV_PATH,
        filename=CSV_PATH.name,
        session_id=session_id,
        user_id=user_id,
    )
    print("CSV_IMPORT", csv_result.to_dict())

    merge_result = merge_session_data(
        session_id=session_id,
        user_id=user_id,
    )
    print("MERGE", merge_result.to_dict())

    analysis_result = run_session_analysis(
        session_id=session_id,
        user_id=user_id,
    )
    result = analysis_result.to_dict()
    print(
        "ANALYSIS",
        {
            "ai_result_id": result["ai_result_id"],
            "session_id": result["session_id"],
            "overall_score": result.get("overall_score"),
            "wellness_status": result.get("wellness_status"),
            "data_quality_score": result.get("data_quality_score"),
            "quality_warnings": result.get("quality_warnings"),
        },
    )

    con = db()
    cur = con.cursor()
    try:
        cur.execute(
            """
            SELECT COUNT(*)
            FROM session_features
            WHERE session_id = %s
            """,
            (session_id,),
        )
        print("SESSION_FEATURES_COUNT", cur.fetchone()[0])

        cur.execute(
            """
            SELECT baseline_date, rmssd_7d, rmssd_14d, rmssd_30d, status
            FROM daily_baselines
            WHERE user_id = %s
            ORDER BY baseline_date DESC
            LIMIT 1
            """,
            (user_id,),
        )
        print("LATEST_BASELINE", cur.fetchone())
    finally:
        cur.close()
        con.close()


def cleanup_session_data(cur, *, session_id: str) -> None:
    tables = [
        "ai_results",
        "session_features",
        "merged_data",
        "merge_jobs",
        "fit_data",
        "csv_data",
        "fit_imports",
        "csv_imports",
        "full_sessions",
    ]

    for table in tables:
        cur.execute(
            f"DELETE FROM {table} WHERE session_id = %s",
            (session_id,),
        )


def main() -> None:
    print("START", datetime.now().isoformat(timespec="seconds"))
    clean_subjects()
    ensure_migrations()
    test_pipeline()


if __name__ == "__main__":
    main()
