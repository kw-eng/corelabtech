from database_postgres import db


def upgrade() -> None:
    connection = db()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                audit_id BIGSERIAL PRIMARY KEY,
                actor_user_id VARCHAR(64),
                actor_role VARCHAR(50),
                action VARCHAR(100) NOT NULL,
                entity_type VARCHAR(80) NOT NULL,
                entity_id VARCHAR(255),
                client_id VARCHAR(64),
                session_id VARCHAR(255),
                outcome VARCHAR(32) NOT NULL DEFAULT 'success',
                details_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                ip_address VARCHAR(64),
                user_agent TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_audit_log_client_created
            ON audit_log(client_id, created_at DESC)
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_audit_log_actor_created
            ON audit_log(actor_user_id, created_at DESC)
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS data_requests (
                request_id BIGSERIAL PRIMARY KEY,
                client_id VARCHAR(64) NOT NULL,
                request_type VARCHAR(32) NOT NULL,
                requested_by VARCHAR(64),
                status VARCHAR(32) NOT NULL DEFAULT 'completed',
                details_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                CONSTRAINT ck_data_requests_type
                    CHECK (request_type IN ('export', 'delete', 'anonymize')),
                CONSTRAINT ck_data_requests_status
                    CHECK (
                        status IN (
                            'received',
                            'processing',
                            'completed',
                            'rejected',
                            'failed'
                        )
                    )
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS consent_records (
                consent_id BIGSERIAL PRIMARY KEY,
                client_id VARCHAR(64) NOT NULL,
                session_id VARCHAR(255),
                consent_type VARCHAR(80) NOT NULL,
                accepted BOOLEAN NOT NULL,
                terms_version VARCHAR(40) NOT NULL,
                recorded_by VARCHAR(64),
                recorded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                withdrawn_at TIMESTAMP,
                metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_consent_client_recorded
            ON consent_records(client_id, recorded_at DESC)
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
