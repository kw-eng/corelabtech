from database_postgres import db


def upgrade() -> None:
    connection = db()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            WITH defaults AS (
                SELECT
                    o.organization_id,
                    l.location_id,
                    p.protocol_id
                FROM organizations o
                JOIN organization_locations l
                    ON l.organization_id = o.organization_id
                   AND l.code = 'MAIN'
                JOIN protocols p
                    ON p.code = 'WELLNESS_1_5'
                   AND p.organization_id = o.organization_id
                WHERE o.code = 'CORELABTECH_DEFAULT'
                LIMIT 1
            ),
            program_rows AS (
                SELECT
                    'RECOVERY_50' AS code,
                    'Recovery 50' AS name,
                    50 AS total_sessions,
                    3 AS frequency_per_week,
                    'Fifty-session wellness response tracking program.' AS description
                UNION ALL
                SELECT
                    'RECOVERY_100',
                    'Recovery 100',
                    100,
                    3,
                    'One-hundred-session longitudinal wellness tracking program.'
            )
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
                d.organization_id,
                d.location_id,
                d.protocol_id,
                pr.code,
                pr.name,
                pr.total_sessions,
                pr.frequency_per_week,
                pr.description
            FROM defaults d
            CROSS JOIN program_rows pr
            ON CONFLICT (organization_id, code)
            DO UPDATE SET
                name = EXCLUDED.name,
                total_sessions = EXCLUDED.total_sessions,
                frequency_per_week = EXCLUDED.frequency_per_week,
                description = EXCLUDED.description,
                is_active = TRUE,
                updated_at = CURRENT_TIMESTAMP
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
