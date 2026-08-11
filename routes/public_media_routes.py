from flask import Blueprint, abort, send_file

from services.i18n_service import current_locale
from services.public_media_service import resolve_public_media_file


public_media_bp = Blueprint("public_media", __name__, url_prefix="/public-media")


@public_media_bp.get("/<path:role>")
def serve_public_media(role: str):
    """Serve a curated public asset without exposing its stored file path."""
    media_file = resolve_public_media_file(role, current_locale())
    if media_file is None:
        abort(404)
    absolute_path, mime_type = media_file
    if not absolute_path.is_file():
        abort(404)
    return send_file(absolute_path, mimetype=mime_type, conditional=True)
