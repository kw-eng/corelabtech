"""Create the persistence table used by the Content Studio media library."""

from database_postgres import db


def upgrade() -> None:
    connection = db()
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS generated_media (
                id BIGSERIAL PRIMARY KEY,
                media_type VARCHAR(32) NOT NULL,
                scene_id VARCHAR(128) NOT NULL,
                character_id VARCHAR(128) NOT NULL,
                version VARCHAR(128) NOT NULL,
                ai_provider VARCHAR(64) NOT NULL,
                prompt TEXT NOT NULL,
                negative_prompt TEXT,
                file_path TEXT NOT NULL,
                file_name VARCHAR(512) NOT NULL,
                mime_type VARCHAR(128),
                width INTEGER,
                height INTEGER,
                duration_seconds DOUBLE PRECISION,
                file_size_bytes BIGINT,
                status VARCHAR(32) NOT NULL DEFAULT 'generated',
                is_final BOOLEAN NOT NULL DEFAULT FALSE,
                notes TEXT,
                created_by INTEGER REFERENCES users(id),
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_generated_media_created ON generated_media(created_at DESC)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_generated_media_creator ON generated_media(created_by, created_at DESC)"
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()
