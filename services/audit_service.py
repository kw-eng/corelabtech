"""Append-only audit helpers for privacy and operational accountability."""

from __future__ import annotations

import json
from typing import Any


def record_audit_event(
    cursor,
    *,
    actor_user_id: str | None,
    actor_role: str | None,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    client_id: str | None = None,
    session_id: str | None = None,
    outcome: str = "success",
    details: dict[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Write one audit event without storing physiology payloads."""

    cursor.execute(
        """
        INSERT INTO audit_log (
            actor_user_id,
            actor_role,
            action,
            entity_type,
            entity_id,
            client_id,
            session_id,
            outcome,
            details_json,
            ip_address,
            user_agent
        )
        VALUES (
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s::jsonb, %s, %s
        )
        """,
        (
            actor_user_id,
            actor_role,
            action,
            entity_type,
            entity_id,
            client_id,
            session_id,
            outcome,
            json.dumps(details or {}, default=str),
            ip_address,
            user_agent,
        ),
    )
