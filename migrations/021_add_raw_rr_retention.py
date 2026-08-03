"""Retain complete raw RR packets and HRV calculation provenance."""

from database_postgres import db


def upgrade() -> None:
    con = db()
    cur = con.cursor()
    try:
        cur.execute(
            """
            ALTER TABLE fit_data
            ADD COLUMN IF NOT EXISTS rr_intervals_json JSONB,
            ADD COLUMN IF NOT EXISTS rr_unit VARCHAR(30)
            """
        )
        cur.execute(
            """
            ALTER TABLE merged_data
            ADD COLUMN IF NOT EXISTS rr_intervals_json JSONB
            """
        )
        cur.execute(
            """
            ALTER TABLE session_features
            ADD COLUMN IF NOT EXISTS hrv_algorithm_version VARCHAR(50),
            ADD COLUMN IF NOT EXISTS hrv_confidence VARCHAR(30)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_fit_data_rr_packets
            ON fit_data(session_id)
            WHERE rr_intervals_json IS NOT NULL
            """
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
