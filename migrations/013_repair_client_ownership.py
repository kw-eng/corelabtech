from database_postgres import db
from repositories.wellness_repository import refresh_daily_baseline


SESSION_OWNED_TABLES = (
    "tests",
    "fit_imports",
    "csv_imports",
    "fit_data",
    "csv_data",
    "merge_jobs",
    "merged_data",
    "ai_results",
    "session_features",
    "hrv_imports",
    "hrv_intervals",
)


def upgrade() -> None:
    """Align historical session data with the canonical client owner."""

    con = db()
    cur = con.cursor()

    try:
        for table in SESSION_OWNED_TABLES:
            cur.execute(
                f"""
                UPDATE {table} AS target
                SET user_id = fs.user_id
                FROM full_sessions fs
                WHERE target.session_id = fs.session_id
                  AND target.user_id IS DISTINCT FROM fs.user_id
                """
            )

        cur.execute(
            """
            DELETE FROM daily_baselines
            WHERE user_id IN (
                SELECT DISTINCT user_id
                FROM full_sessions
                WHERE user_id IS NOT NULL
            )
            """
        )

        cur.execute(
            """
            SELECT
                user_id,
                MAX(COALESCE(window_start::date, created_at::date))
            FROM session_features
            WHERE user_id IS NOT NULL
              AND session_id NOT LIKE 'PIPELINE_VALIDATION_%%'
            GROUP BY user_id
            """
        )
        baseline_targets = cur.fetchall()

        for user_id, baseline_date in baseline_targets:
            if baseline_date:
                refresh_daily_baseline(
                    cur,
                    user_id=user_id,
                    baseline_date=baseline_date,
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
