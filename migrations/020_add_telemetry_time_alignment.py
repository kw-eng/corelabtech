"""Preserve source timestamps and persist merge alignment provenance."""

from database_postgres import db


def add_columns(cursor, table: str, definitions: tuple[str, ...]) -> None:
    for definition in definitions:
        cursor.execute(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {definition}"
        )


def upgrade() -> None:
    con = db()
    cur = con.cursor()
    try:
        import_columns = (
            "source_timezone VARCHAR(80)",
            "timestamp_normalization_version VARCHAR(50)",
        )
        raw_columns = (
            "original_timestamp TEXT",
            "source_timezone VARCHAR(80)",
            "timestamp_utc TIMESTAMPTZ",
        )

        add_columns(cur, "csv_imports", import_columns)
        add_columns(cur, "fit_imports", import_columns)
        add_columns(cur, "csv_data", raw_columns)
        add_columns(cur, "fit_data", raw_columns)
        add_columns(
            cur,
            "merged_data",
            (
                "timestamp_utc TIMESTAMPTZ",
                "fit_timestamp_utc TIMESTAMPTZ",
                "csv_timestamp_utc TIMESTAMPTZ",
                "time_alignment_method VARCHAR(50)",
                "time_alignment_quality VARCHAR(30)",
            ),
        )
        add_columns(
            cur,
            "merge_jobs",
            (
                "time_alignment_method VARCHAR(50)",
                "time_alignment_quality VARCHAR(30)",
            ),
        )

        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_csv_data_timestamp_utc
            ON csv_data(timestamp_utc)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_fit_data_timestamp_utc
            ON fit_data(timestamp_utc)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_merged_data_timestamp_utc
            ON merged_data(timestamp_utc)
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
