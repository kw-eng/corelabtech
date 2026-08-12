from __future__ import annotations

import logging
import uuid

from flask import (
    Blueprint,
    jsonify,
    render_template,
    request,
    send_file,
)
from flask_login import current_user, login_required
from security.limiter import limiter

from datetime import datetime, timezone

from services.generated_media_service import (
    GeneratedMediaInput,
    get_generated_media,
    list_generated_media,
    register_generated_media,
    create_mock_generated_media,
    resolve_media_path,
    update_generated_media_status,
    generated_media_presentation,
)
from services.prompt_builder_service import build_generation_prompt
from services.content_provider_capabilities import (
    public_provider_capabilities,
    supports_output_type,
)


logger = logging.getLogger(__name__)


content_studio_bp = Blueprint(
    "content_studio",
    __name__,
    url_prefix="/content-studio",
)


def _parse_optional_boolean(
    value: str | None,
) -> bool | None:
    if value is None or value == "":
        return None

    normalized = value.strip().lower()

    if normalized in {"true", "1", "yes"}:
        return True

    if normalized in {"false", "0", "no"}:
        return False

    raise ValueError(
        "Boolean value must be true or false"
    )

ROUTE_OPEN = chr(60)
ROUTE_CLOSE = chr(62)
# ==========================================================
# PAGE ROUTES
# ==========================================================


@content_studio_bp.get("")
@login_required
def content_studio_page():
    return render_template(
        "content_studio/dashboard.html"
    )


@content_studio_bp.get("/characters")
@login_required
def characters_page():
    return render_template(
        "content_studio/characters.html"
    )


@content_studio_bp.get(
    f"/characters/{ROUTE_OPEN}string:character{ROUTE_CLOSE}"
)
@login_required
def character_details_page(
    character: str,
):
    return render_template(
        "content_studio/character_details.html",
        character=character,
        image_count=0,
        video_count=0,
    )


@content_studio_bp.get("/scenes")
@login_required
def scenes_page():
    scenes = []

    return render_template(
        "content_studio/scenes.html",
        scenes=scenes,
    )


@content_studio_bp.get("/prompt-builder")
@login_required
def prompt_builder_page():
    return render_template(
        "content_studio/prompt_builder.html"
    )


@content_studio_bp.get("/storyboards")
@login_required
def storyboards_page():
    storyboards = []

    return render_template(
        "content_studio/storyboards.html",
        storyboards=storyboards,
    )


@content_studio_bp.get("/generate")
@login_required
def generate_page():
    return render_template(
        "content_studio/generate.html"
    )


@content_studio_bp.get("/media")
@login_required
def media_page():
    return render_template(
        "content_studio/generated_media.html",
        media_list=[],
    )


@content_studio_bp.get("/settings")
@login_required
def settings_page():
    return render_template(
        "content_studio/settings.html"
    )

# ==========================================================
# GENERATION API
# ==========================================================


@content_studio_bp.get("/api/provider-capabilities")
@login_required
def get_provider_capabilities():
    """Return the output types the currently configured providers can create."""

    return jsonify({"status": "success", "providers": public_provider_capabilities()})


@content_studio_bp.post(
    "/api/generation-jobs"
)
@login_required
@limiter.limit("10 per hour")
def create_generation_job():
    payload = request.get_json(
        silent=True
    ) or {}

    required_fields = {
        "provider",
        "output_type",
        "character_id",
        "scene_id",
    }

    missing_fields = sorted(
        field
        for field in required_fields
        if not payload.get(field)
    )

    if missing_fields:
        return jsonify({
            "status": "error",
            "error": "Missing required fields",
            "fields": missing_fields,
        }), 400

    provider = payload["provider"]

    if provider != "mock":
        return jsonify({
            "status": "error",
            "error": (
                "Provider is not connected yet."
            ),
        }), 400

    if not supports_output_type(provider, payload["output_type"]):
        return jsonify({
            "status": "error",
            "error": "The selected provider does not support this output type.",
        }), 400

    job_id = str(uuid.uuid4())
    try:
        media = create_mock_generated_media(
            GeneratedMediaInput(
                media_type="image",
                scene_id=payload["scene_id"],
                character_id=payload["character_id"],
                version="mock",
                ai_provider="mock",
                prompt=build_generation_prompt(
                    character_id=payload["character_id"],
                    scene_id=payload["scene_id"],
                    output_type=payload["output_type"],
                ),
                file_path="assets/athlete/generated/development/pending.svg",
                created_by=getattr(current_user, "id", None),
            ),
            generation_job_id=job_id,
        )
    except Exception:
        logger.exception("Mock generation failed")
        return jsonify({"status": "error", "error": "Mock media generation failed."}), 500

    job = {
        "id": job_id,
        "provider": provider,
        "output_type": payload[
            "output_type"
        ],
        "character_id": payload[
            "character_id"
        ],
        "scene_id": payload[
            "scene_id"
        ],
        "status": "completed",
        "progress_percent": 100,
        "kind": "synchronous_development_mock",
        "media_id": media["id"],
    }

    logger.info(
        "Mock generation job created: %s",
        job,
    )

    return jsonify({
        "status": "success",
        "job": job,
        "media": generated_media_presentation(media),
    }), 201

# ==========================================================
# GENERATED MEDIA API
# ==========================================================


@content_studio_bp.get("/api/media")
@login_required
def list_media():
    try:
        media = list_generated_media(
            media_type=request.args.get("type"),
            scene_id=request.args.get("scene"),
            character_id=request.args.get(
                "character"
            ),
            status=request.args.get("status"),
            is_final=_parse_optional_boolean(
                request.args.get("is_final")
            ),
            created_by=getattr(current_user, "id", None),
            limit=request.args.get(
                "limit",
                100,
                type=int,
            ),
            offset=request.args.get(
                "offset",
                0,
                type=int,
            ),
        )

        return jsonify({
            "status": "success",
            "count": len(media),
            "media": [generated_media_presentation(item) for item in media],
        })

    except ValueError as error:
        return jsonify({
            "status": "error",
            "error": str(error),
        }), 400

    except Exception:
        logger.exception(
            "Unable to load generated media"
        )

        return jsonify({
            "status": "error",
            "error": "Unable to load generated media",
        }), 500


@content_studio_bp.post("/api/media")
@login_required
def create_media_record():
    payload = request.get_json(
        silent=True
    ) or {}

    required_fields = {
        "media_type",
        "scene_id",
        "character_id",
        "version",
        "ai_provider",
        "file_path",
    }

    missing_fields = sorted(
        field
        for field in required_fields
        if not payload.get(field)
    )

    if missing_fields:
        return jsonify({
            "status": "error",
            "error": "Missing required fields",
            "fields": missing_fields,
        }), 400

    if getattr(current_user, "role", None) != "admin":
        return jsonify({
            "status": "error",
            "error": "Direct media registration is restricted to administrators.",
        }), 403

    try:
        media = register_generated_media(
            GeneratedMediaInput(
                media_type=payload["media_type"],
                scene_id=payload["scene_id"],
                character_id=payload["character_id"],
                version=payload["version"],
                ai_provider=payload["ai_provider"],
                prompt=build_generation_prompt(
                    character_id=payload["character_id"],
                    scene_id=payload["scene_id"],
                    output_type=payload["media_type"],
                ),
                negative_prompt=payload.get(
                    "negative_prompt"
                ),
                file_path=payload["file_path"],
                mime_type=payload.get(
                    "mime_type"
                ),
                width=payload.get(
                    "width"
                ),
                height=payload.get(
                    "height"
                ),
                duration_seconds=payload.get(
                    "duration_seconds"
                ),
                status=payload.get(
                    "status",
                    "generated",
                ),
                is_final=bool(
                    payload.get(
                        "is_final",
                        False,
                    )
                ),
                notes=payload.get(
                    "notes"
                ),
                created_by=getattr(
                    current_user,
                    "id",
                    None,
                ),
            )
        )

        return jsonify({
            "status": "success",
            "media": generated_media_presentation(media),
        }), 201

    except ValueError as error:
        return jsonify({
            "status": "error",
            "error": str(error),
        }), 400

    except Exception:
        logger.exception(
            "Unable to register generated media"
        )

        return jsonify({
            "status": "error",
            "error": (
                "Unable to register generated media"
            ),
        }), 500


@content_studio_bp.patch(
    f"/api/media/{ROUTE_OPEN}int:media_id{ROUTE_CLOSE}"
)
@login_required
def update_media_record(
    media_id: int,
):
    payload = request.get_json(
        silent=True
    ) or {}

    status = payload.get("status")

    if not status:
        return jsonify({
            "status": "error",
            "error": "status is required",
        }), 400

    requested_final = payload.get("is_final")
    privileged_lifecycle = status in {"approved", "published"} or requested_final is True
    if privileged_lifecycle and getattr(current_user, "role", None) != "admin":
        return jsonify({
            "status": "error",
            "error": "Only administrators can approve, publish, or finalize media.",
        }), 403

    try:
        media = update_generated_media_status(
            media_id,
            status=status,
            is_final=(
                bool(payload["is_final"])
                if "is_final" in payload
                else None
            ),
            created_by=getattr(current_user, "id", None),
            notes=(
                payload.get("notes")
                if "notes" in payload
                else None
            ),
        )

        if media is None:
            return jsonify({
                "status": "error",
                "error": "Media record not found",
            }), 404

        return jsonify({
            "status": "success",
            "media": generated_media_presentation(media),
        })

    except ValueError as error:
        return jsonify({
            "status": "error",
            "error": str(error),
        }), 400

    except Exception:
        logger.exception(
            "Unable to update generated media"
        )

        return jsonify({
            "status": "error",
            "error": (
                "Unable to update generated media"
            ),
        }), 500


@content_studio_bp.get(
    f"/api/media/{ROUTE_OPEN}int:media_id{ROUTE_CLOSE}/file"
)
@login_required
def serve_media_file(
    media_id: int,
):
    media = get_generated_media(
        media_id,
        created_by=getattr(current_user, "id", None),
    )

    if media is None:
        return jsonify({
            "status": "error",
            "error": "Media record not found",
        }), 404

    try:
        absolute_path = resolve_media_path(
            media["file_path"]
        )

    except ValueError as error:
        return jsonify({
            "status": "error",
            "error": str(error),
        }), 400

    if not absolute_path.is_file():
        return jsonify({
            "status": "error",
            "error": (
                "Media file does not exist"
            ),
        }), 404

    return send_file(
        absolute_path,
        mimetype=media.get("mime_type"),
        conditional=True,
        download_name=media.get("file_name"),
    )
