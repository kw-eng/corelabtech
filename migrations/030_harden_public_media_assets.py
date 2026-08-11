"""Harden public-media mappings created before explicit lifecycle safeguards."""

from database_postgres import db


def upgrade() -> None:
    connection = db()
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            ALTER TABLE public_media_assets
            DROP CONSTRAINT IF EXISTS public_media_assets_media_id_fkey,
            DROP CONSTRAINT IF EXISTS public_media_assets_poster_media_id_fkey,
            DROP CONSTRAINT IF EXISTS fk_public_media_assets_media,
            DROP CONSTRAINT IF EXISTS fk_public_media_assets_poster,
            DROP CONSTRAINT IF EXISTS ck_public_media_assets_alt_text_en_nonblank,
            DROP CONSTRAINT IF EXISTS ck_public_media_assets_alt_text_pl_nonblank
            """
        )
        cursor.execute(
            """
            ALTER TABLE public_media_assets
            ADD CONSTRAINT fk_public_media_assets_media
                FOREIGN KEY (media_id) REFERENCES generated_media(id) ON DELETE RESTRICT,
            ADD CONSTRAINT fk_public_media_assets_poster
                FOREIGN KEY (poster_media_id) REFERENCES generated_media(id) ON DELETE RESTRICT
            """
        )
        cursor.execute(
            """
            ALTER TABLE public_media_assets
            ADD CONSTRAINT ck_public_media_assets_alt_text_en_nonblank
                CHECK (length(btrim(alt_text_en)) > 0),
            ADD CONSTRAINT ck_public_media_assets_alt_text_pl_nonblank
                CHECK (length(btrim(alt_text_pl)) > 0)
            """
        )
        cursor.execute(
            """
            CREATE OR REPLACE FUNCTION touch_public_media_assets_updated_at()
            RETURNS trigger AS $$
            BEGIN
                NEW.updated_at = CURRENT_TIMESTAMP;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
        cursor.execute(
            """
            DROP TRIGGER IF EXISTS trg_public_media_assets_updated_at
            ON public_media_assets
            """
        )
        cursor.execute(
            """
            CREATE TRIGGER trg_public_media_assets_updated_at
            BEFORE UPDATE ON public_media_assets
            FOR EACH ROW EXECUTE FUNCTION touch_public_media_assets_updated_at()
            """
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()
