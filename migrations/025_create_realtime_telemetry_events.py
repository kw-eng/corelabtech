"""Persist bounded realtime telemetry per authorized wellness session."""

from database_postgres import db


def upgrade() -> None:
    connection = db()
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS realtime_telemetry_events (
                id BIGSERIAL PRIMARY KEY,
                session_id VARCHAR(255) NOT NULL,
                client_id VARCHAR(255) NOT NULL,
                organization_id INTEGER,
                location_id INTEGER,
                recorded_by_user_id VARCHAR(255) NOT NULL,
                recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                heart_rate_bpm DOUBLE PRECISION,
                pulse_rate_bpm DOUBLE PRECISION,
                spo2 DOUBLE PRECISION,
                pressure_ata DOUBLE PRECISION,
                chamber_temperature_c DOUBLE PRECISION,
                source_type VARCHAR(50) NOT NULL DEFAULT 'unknown',
                measurement_method VARCHAR(30) NOT NULL DEFAULT 'unknown',
                signal_quality VARCHAR(30) NOT NULL DEFAULT 'unknown',
                CONSTRAINT realtime_telemetry_has_measurement CHECK (
                    heart_rate_bpm IS NOT NULL
                    OR pulse_rate_bpm IS NOT NULL
                    OR spo2 IS NOT NULL
                    OR pressure_ata IS NOT NULL
                    OR chamber_temperature_c IS NOT NULL
                )
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_realtime_telemetry_session_time
            ON realtime_telemetry_events(session_id, recorded_at DESC, id DESC)
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_realtime_telemetry_org_time
            ON realtime_telemetry_events(organization_id, recorded_at DESC)
            """
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


if __name__ == "__main__":
    upgrade()
