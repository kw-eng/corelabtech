from database_postgres import db


def upgrade() -> None:
    connection = db()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS organizations (
                organization_id BIGSERIAL PRIMARY KEY,
                code VARCHAR(80) UNIQUE NOT NULL,
                name VARCHAR(180) NOT NULL,
                product_mode VARCHAR(32) NOT NULL DEFAULT 'wellness',
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT ck_organizations_product_mode
                    CHECK (product_mode IN ('wellness', 'research', 'internal'))
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS organization_locations (
                location_id BIGSERIAL PRIMARY KEY,
                organization_id BIGINT NOT NULL
                    REFERENCES organizations(organization_id),
                code VARCHAR(80) NOT NULL,
                name VARCHAR(180) NOT NULL,
                address TEXT,
                timezone VARCHAR(80) NOT NULL DEFAULT 'Europe/Warsaw',
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (organization_id, code)
            )
            """
        )
        cursor.execute(
            """
            INSERT INTO organizations (code, name, product_mode)
            VALUES ('CORELABTECH_DEFAULT', 'CoreLabTech Wellness', 'wellness')
            ON CONFLICT (code) DO NOTHING
            """
        )
        cursor.execute(
            """
            INSERT INTO organization_locations (
                organization_id,
                code,
                name
            )
            SELECT organization_id, 'MAIN', 'Main Location'
            FROM organizations
            WHERE code = 'CORELABTECH_DEFAULT'
            ON CONFLICT (organization_id, code) DO NOTHING
            """
        )

        for table in ("users", "chambers", "protocols", "full_sessions"):
            cursor.execute(
                f"""
                ALTER TABLE {table}
                    ADD COLUMN IF NOT EXISTS organization_id BIGINT
                        REFERENCES organizations(organization_id)
                """
            )

        for table in ("users", "chambers", "full_sessions"):
            cursor.execute(
                f"""
                ALTER TABLE {table}
                    ADD COLUMN IF NOT EXISTS location_id BIGINT
                        REFERENCES organization_locations(location_id)
                """
            )

        cursor.execute(
            """
            ALTER TABLE protocols
                ADD COLUMN IF NOT EXISTS protocol_version INTEGER
                    NOT NULL DEFAULT 1
            """
        )
        cursor.execute(
            """
            ALTER TABLE full_sessions
                ADD COLUMN IF NOT EXISTS protocol_version INTEGER
                    NOT NULL DEFAULT 1,
                ADD COLUMN IF NOT EXISTS execution_status VARCHAR(32)
                    NOT NULL DEFAULT 'as_planned',
                ADD COLUMN IF NOT EXISTS deviation_reason TEXT,
                ADD COLUMN IF NOT EXISTS deviation_approved_by VARCHAR(64)
                    REFERENCES users(user_id)
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS wellness_programs (
                program_id BIGSERIAL PRIMARY KEY,
                organization_id BIGINT NOT NULL
                    REFERENCES organizations(organization_id),
                location_id BIGINT
                    REFERENCES organization_locations(location_id),
                protocol_id BIGINT NOT NULL REFERENCES protocols(protocol_id),
                code VARCHAR(80) NOT NULL,
                name VARCHAR(180) NOT NULL,
                total_sessions INTEGER NOT NULL,
                frequency_per_week INTEGER,
                description TEXT,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (organization_id, code),
                CONSTRAINT ck_wellness_program_total
                    CHECK (total_sessions BETWEEN 1 AND 365),
                CONSTRAINT ck_wellness_program_frequency
                    CHECK (
                        frequency_per_week IS NULL
                        OR frequency_per_week BETWEEN 1 AND 14
                    )
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS client_programs (
                enrollment_id BIGSERIAL PRIMARY KEY,
                program_id BIGINT NOT NULL
                    REFERENCES wellness_programs(program_id),
                client_id VARCHAR(64) NOT NULL REFERENCES users(user_id),
                status VARCHAR(32) NOT NULL DEFAULT 'active',
                started_at DATE NOT NULL DEFAULT CURRENT_DATE,
                completed_at DATE,
                created_by VARCHAR(64) REFERENCES users(user_id),
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT ck_client_program_status
                    CHECK (status IN ('active', 'completed', 'paused', 'cancelled'))
            )
            """
        )
        cursor.execute(
            """
            ALTER TABLE full_sessions
                ADD COLUMN IF NOT EXISTS program_enrollment_id BIGINT
                    REFERENCES client_programs(enrollment_id)
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS session_segments (
                segment_id BIGSERIAL PRIMARY KEY,
                session_id VARCHAR(255) NOT NULL
                    REFERENCES full_sessions(session_id) ON DELETE CASCADE,
                sequence_no INTEGER NOT NULL,
                phase VARCHAR(32) NOT NULL,
                planned_duration_min INTEGER,
                actual_duration_min INTEGER NOT NULL,
                target_ata DOUBLE PRECISION,
                actual_ata DOUBLE PRECISION,
                oxygen_mode VARCHAR(80),
                note TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (session_id, sequence_no),
                CONSTRAINT ck_session_segment_phase
                    CHECK (
                        phase IN (
                            'compression',
                            'exposure',
                            'air_break',
                            'decompression',
                            'recovery',
                            'other'
                        )
                    ),
                CONSTRAINT ck_session_segment_duration
                    CHECK (actual_duration_min BETWEEN 0 AND 360)
            )
            """
        )

        cursor.execute(
            """
            WITH defaults AS (
                SELECT
                    o.organization_id,
                    l.location_id
                FROM organizations o
                JOIN organization_locations l
                    ON l.organization_id = o.organization_id
                WHERE o.code = 'CORELABTECH_DEFAULT'
                  AND l.code = 'MAIN'
                LIMIT 1
            )
            UPDATE users u
            SET
                organization_id = COALESCE(u.organization_id, d.organization_id),
                location_id = COALESCE(u.location_id, d.location_id)
            FROM defaults d
            WHERE u.organization_id IS NULL OR u.location_id IS NULL
            """
        )
        cursor.execute(
            """
            WITH defaults AS (
                SELECT
                    o.organization_id,
                    l.location_id
                FROM organizations o
                JOIN organization_locations l
                    ON l.organization_id = o.organization_id
                WHERE o.code = 'CORELABTECH_DEFAULT'
                  AND l.code = 'MAIN'
                LIMIT 1
            )
            UPDATE chambers c
            SET
                organization_id = COALESCE(c.organization_id, d.organization_id),
                location_id = COALESCE(c.location_id, d.location_id)
            FROM defaults d
            WHERE c.organization_id IS NULL OR c.location_id IS NULL
            """
        )
        cursor.execute(
            """
            UPDATE protocols p
            SET organization_id = o.organization_id
            FROM organizations o
            WHERE o.code = 'CORELABTECH_DEFAULT'
              AND p.organization_id IS NULL
            """
        )
        cursor.execute(
            """
            UPDATE full_sessions fs
            SET
                organization_id = COALESCE(fs.organization_id, u.organization_id),
                location_id = COALESCE(fs.location_id, u.location_id)
            FROM users u
            WHERE u.user_id = fs.user_id
              AND (fs.organization_id IS NULL OR fs.location_id IS NULL)
            """
        )
        cursor.execute(
            """
            INSERT INTO wellness_programs (
                organization_id,
                location_id,
                protocol_id,
                code,
                name,
                total_sessions,
                frequency_per_week,
                description
            )
            SELECT
                o.organization_id,
                l.location_id,
                p.protocol_id,
                'RECOVERY_20',
                'Recovery 20',
                20,
                3,
                'Twenty-session wellness recovery program.'
            FROM organizations o
            JOIN organization_locations l
                ON l.organization_id = o.organization_id
               AND l.code = 'MAIN'
            JOIN protocols p
                ON p.code = 'WELLNESS_1_5'
            WHERE o.code = 'CORELABTECH_DEFAULT'
            ON CONFLICT (organization_id, code) DO NOTHING
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_users_organization
            ON users(organization_id, role, is_active)
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_sessions_organization
            ON full_sessions(organization_id, location_id, created_at)
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_client_programs_client
            ON client_programs(client_id, status)
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
