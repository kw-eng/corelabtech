"""Add explicit measurement provenance without rewriting historical telemetry."""

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
        add_columns(
            cur,
            "csv_imports",
            (
                "device_type VARCHAR(50)",
                "device_model VARCHAR(120)",
                "measurement_method VARCHAR(30)",
                "telemetry_schema_version VARCHAR(50)",
            ),
        )
        add_columns(
            cur,
            "fit_imports",
            (
                "device_type VARCHAR(50)",
                "device_model VARCHAR(120)",
                "measurement_method VARCHAR(30)",
                "telemetry_schema_version VARCHAR(50)",
            ),
        )
        add_columns(
            cur,
            "csv_data",
            (
                "pulse_rate_bpm DOUBLE PRECISION",
                "heart_rate_bpm DOUBLE PRECISION",
                "device_type VARCHAR(50)",
                "device_model VARCHAR(120)",
                "measurement_method VARCHAR(30)",
                "signal_quality VARCHAR(30)",
                "quality_reason VARCHAR(120)",
            ),
        )
        add_columns(
            cur,
            "fit_data",
            (
                "pulse_rate_bpm DOUBLE PRECISION",
                "heart_rate_bpm DOUBLE PRECISION",
                "device_type VARCHAR(50)",
                "device_model VARCHAR(120)",
                "measurement_method VARCHAR(30)",
                "signal_quality VARCHAR(30)",
                "quality_reason VARCHAR(120)",
            ),
        )
        add_columns(
            cur,
            "merged_data",
            (
                "pulse_rate_bpm DOUBLE PRECISION",
                "heart_rate_bpm DOUBLE PRECISION",
                "hr_source_type VARCHAR(50)",
                "hr_measurement_method VARCHAR(30)",
                "hr_signal_quality VARCHAR(30)",
                "pulse_source_type VARCHAR(50)",
                "pulse_measurement_method VARCHAR(30)",
                "pulse_signal_quality VARCHAR(30)",
                "telemetry_schema_version VARCHAR(50)",
            ),
        )

        # Historical rows retain their original values and explicitly remain
        # unknown instead of being relabelled as ECG or PPG without evidence.
        cur.execute(
            """
            UPDATE csv_data
            SET device_type = COALESCE(device_type, 'unknown'),
                measurement_method = COALESCE(measurement_method, 'unknown'),
                signal_quality = COALESCE(signal_quality, 'unknown'),
                quality_reason = COALESCE(quality_reason, 'historical_import')
            WHERE device_type IS NULL
               OR measurement_method IS NULL
               OR signal_quality IS NULL
               OR quality_reason IS NULL
            """
        )
        cur.execute(
            """
            UPDATE fit_data
            SET device_type = COALESCE(device_type, 'unknown'),
                measurement_method = COALESCE(measurement_method, 'unknown'),
                signal_quality = COALESCE(signal_quality, 'unknown'),
                quality_reason = COALESCE(quality_reason, 'historical_import')
            WHERE device_type IS NULL
               OR measurement_method IS NULL
               OR signal_quality IS NULL
               OR quality_reason IS NULL
            """
        )

        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_csv_data_device_type
            ON csv_data(device_type)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_fit_data_device_type
            ON fit_data(device_type)
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
