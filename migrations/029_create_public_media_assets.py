"""Create a separately curated mapping from approved media to public asset roles."""

from database_postgres import db


def upgrade() -> None:
    connection = db()
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS public_media_assets (
                role VARCHAR(128) PRIMARY KEY,
                media_id BIGINT NOT NULL,
                poster_media_id BIGINT,
                alt_text_en TEXT NOT NULL,
                alt_text_pl TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_public_media_assets_media
                    FOREIGN KEY (media_id) REFERENCES generated_media(id) ON DELETE RESTRICT,
                CONSTRAINT fk_public_media_assets_poster
                    FOREIGN KEY (poster_media_id) REFERENCES generated_media(id) ON DELETE RESTRICT
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_public_media_assets_media ON public_media_assets(media_id)"
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
