from database_postgres import db


def upgrade() -> None:
    connection = db()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS chambers (
                chamber_id BIGSERIAL PRIMARY KEY,
                code VARCHAR(80) UNIQUE NOT NULL,
                name VARCHAR(160) NOT NULL,
                location VARCHAR(255),
                manufacturer VARCHAR(160),
                model VARCHAR(160),
                serial_number VARCHAR(160),
                max_ata DOUBLE PRECISION NOT NULL DEFAULT 1.5,
                pressure_input_unit VARCHAR(32) NOT NULL DEFAULT 'kpa_gauge',
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT ck_chambers_max_ata
                    CHECK (max_ata >= 1.0 AND max_ata <= 3.0),
                CONSTRAINT ck_chambers_pressure_unit
                    CHECK (
                        pressure_input_unit IN (
                            'ata',
                            'kpa_gauge',
                            'kpa_absolute'
                        )
                    )
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS protocols (
                protocol_id BIGSERIAL PRIMARY KEY,
                code VARCHAR(80) UNIQUE NOT NULL,
                name VARCHAR(160) NOT NULL,
                mode VARCHAR(32) NOT NULL DEFAULT 'wellness',
                target_ata DOUBLE PRECISION,
                planned_duration_min INTEGER,
                compression_time_min INTEGER,
                exposure_time_min INTEGER,
                decompression_time_min INTEGER,
                oxygen_mode VARCHAR(80),
                oxygen_flow_lpm DOUBLE PRECISION,
                oxygen_percent DOUBLE PRECISION,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT ck_protocols_mode
                    CHECK (mode IN ('wellness', 'research', 'legacy')),
                CONSTRAINT ck_protocols_target_ata
                    CHECK (
                        target_ata IS NULL
                        OR (target_ata >= 1.0 AND target_ata <= 3.0)
                    ),
                CONSTRAINT ck_protocols_oxygen_percent
                    CHECK (
                        oxygen_percent IS NULL
                        OR (oxygen_percent >= 20.0 AND oxygen_percent <= 100.0)
                    )
            )
            """
        )

        cursor.execute(
            """
            INSERT INTO chambers (
                code,
                name,
                max_ata,
                pressure_input_unit
            )
            VALUES (
                'MAIN_CHAMBER',
                'Main Chamber',
                1.5,
                'kpa_gauge'
            )
            ON CONFLICT (code) DO NOTHING
            """
        )

        cursor.execute(
            """
            INSERT INTO protocols (
                code,
                name,
                mode,
                target_ata,
                planned_duration_min,
                compression_time_min,
                exposure_time_min,
                decompression_time_min,
                oxygen_mode
            )
            VALUES
                (
                    'WELLNESS_1_3',
                    'Wellness 1.3 ATA',
                    'wellness',
                    1.3,
                    60,
                    10,
                    40,
                    10,
                    'configured_by_operator'
                ),
                (
                    'WELLNESS_1_5',
                    'Wellness 1.5 ATA',
                    'wellness',
                    1.5,
                    120,
                    15,
                    90,
                    15,
                    'configured_by_operator'
                ),
                (
                    'LEGACY_UNSPECIFIED',
                    'Legacy / protocol not recorded',
                    'legacy',
                    NULL,
                    NULL,
                    NULL,
                    NULL,
                    NULL,
                    NULL
                )
            ON CONFLICT (code) DO NOTHING
            """
        )

        cursor.execute(
            """
            ALTER TABLE full_sessions
                ADD COLUMN IF NOT EXISTS chamber_id BIGINT
                    REFERENCES chambers(chamber_id),
                ADD COLUMN IF NOT EXISTS protocol_id BIGINT
                    REFERENCES protocols(protocol_id),
                ADD COLUMN IF NOT EXISTS target_ata DOUBLE PRECISION,
                ADD COLUMN IF NOT EXISTS actual_ata DOUBLE PRECISION,
                ADD COLUMN IF NOT EXISTS pressure_input_value DOUBLE PRECISION,
                ADD COLUMN IF NOT EXISTS pressure_input_unit VARCHAR(32),
                ADD COLUMN IF NOT EXISTS pressure_deviation DOUBLE PRECISION
            """
        )

        cursor.execute(
            """
            ALTER TABLE session_features
                ADD COLUMN IF NOT EXISTS protocol_id BIGINT
                    REFERENCES protocols(protocol_id),
                ADD COLUMN IF NOT EXISTS target_ata DOUBLE PRECISION,
                ADD COLUMN IF NOT EXISTS actual_ata DOUBLE PRECISION
            """
        )

        cursor.execute(
            """
            ALTER TABLE daily_baselines
                ADD COLUMN IF NOT EXISTS protocol_id BIGINT
                    REFERENCES protocols(protocol_id)
            """
        )

        cursor.execute(
            """
            UPDATE full_sessions
            SET protocol_id = (
                SELECT protocol_id
                FROM protocols
                WHERE code = 'LEGACY_UNSPECIFIED'
            )
            WHERE protocol_id IS NULL
            """
        )
        cursor.execute(
            """
            UPDATE session_features
            SET protocol_id = (
                SELECT protocol_id
                FROM protocols
                WHERE code = 'LEGACY_UNSPECIFIED'
            )
            WHERE protocol_id IS NULL
            """
        )
        cursor.execute(
            """
            UPDATE daily_baselines
            SET protocol_id = (
                SELECT protocol_id
                FROM protocols
                WHERE code = 'LEGACY_UNSPECIFIED'
            )
            WHERE protocol_id IS NULL
            """
        )

        cursor.execute(
            """
            ALTER TABLE daily_baselines
            DROP CONSTRAINT IF EXISTS uq_daily_baselines_user_date
            """
        )
        cursor.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS
                uq_daily_baselines_user_date_protocol
            ON daily_baselines(user_id, baseline_date, protocol_id)
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_full_sessions_protocol
            ON full_sessions(user_id, protocol_id, created_at)
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_session_features_protocol
            ON session_features(user_id, protocol_id, created_at)
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
