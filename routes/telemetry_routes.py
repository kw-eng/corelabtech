"""Authorized, session-scoped realtime telemetry API."""

from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required
from flask_wtf.csrf import generate_csrf

from auth.access_policy import can_access_client_record
from auth.decorators import role_required
from database_postgres import db
from repositories.realtime_telemetry_repository import (
    create_realtime_event,
    get_realtime_session_context,
    list_realtime_events,
    normalize_realtime_payload,
)
from security.limiter import limiter
from security.csrf import csrf


telemetry_bp = Blueprint("telemetry", __name__)
_REALTIME_LIMIT = "240 per minute"


@telemetry_bp.route("/api/realtime-telemetry/csrf-token")
@login_required
def realtime_telemetry_csrf_token():
    """Issue a same-session CSRF token for authenticated live telemetry clients."""

    return jsonify({"csrf_token": generate_csrf()})


def can_access_realtime_session(session_id: str) -> dict | None:
    connection = db()
    cursor = connection.cursor()
    try:
        context = get_realtime_session_context(cursor, session_id=session_id)
    finally:
        cursor.close()
        connection.close()

    if not context:
        return None
    if not can_access_client_record(
        requesting_role=current_user.role,
        requesting_user_id=current_user.user_id,
        client_id=context["client_id"],
        requesting_organization_id=current_user.organization_id,
    ):
        return None
    return context


@telemetry_bp.route("/api/sessions/<session_id>/realtime-telemetry", methods=["POST"])
@login_required
@role_required("operator", "admin")
@limiter.limit(_REALTIME_LIMIT)
def create_session_realtime_telemetry(session_id: str):
    """Record one bounded measurement for a client owned by the operator's org."""

    data = request.get_json(silent=True)
    client_id = str((data or {}).get("client_id") or "").strip()
    if not session_id.strip() or not client_id:
        return jsonify({"error": "session_id and client_id are required"}), 400
    if not can_access_client_record(
        requesting_role=current_user.role,
        requesting_user_id=current_user.user_id,
        client_id=client_id,
        requesting_organization_id=current_user.organization_id,
    ):
        return jsonify({"error": "forbidden"}), 403
    try:
        payload = normalize_realtime_payload(data or {})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    connection = db()
    cursor = connection.cursor()
    try:
        event = create_realtime_event(
            cursor,
            session_id=session_id.strip(),
            client_id=client_id,
            organization_id=current_user.organization_id,
            location_id=current_user.location_id,
            recorded_by_user_id=current_user.user_id,
            payload=payload,
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()

    return jsonify({"status": "saved", "event": {**event, **payload}}), 201


@telemetry_bp.route("/api/sessions/<session_id>/realtime-telemetry", methods=["GET"])
@login_required
@role_required("viewer", "operator", "researcher", "admin")
@limiter.limit("120 per minute")
def get_session_realtime_telemetry(session_id: str):
    """Return only the bounded live series for an authorized session."""

    context = can_access_realtime_session(session_id)
    if not context:
        return jsonify({"error": "session not found"}), 404
    connection = db()
    cursor = connection.cursor()
    try:
        events = list_realtime_events(cursor, session_id=session_id)
    finally:
        cursor.close()
        connection.close()
    return jsonify(
        {
            "status": "ok",
            "session_id": session_id,
            "client_id": context["client_id"],
            "events": events,
        }
    )


@telemetry_bp.route("/api/push_telemetry", methods=["POST"])
@telemetry_bp.route("/api/telemetry")
@telemetry_bp.route("/api/telemetry_buffer")
@csrf.exempt
@login_required
def deprecated_global_telemetry():
    """Prevent legacy clients from writing or reading a shared telemetry buffer."""

    return jsonify(
        {
            "error": "global telemetry is retired; use the session-scoped realtime endpoint",
            "endpoint": "/api/sessions/<session_id>/realtime-telemetry",
        }
    ), 410
