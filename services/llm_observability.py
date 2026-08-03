"""Privacy-preserving operational metrics for optional LLM narrations."""

from __future__ import annotations

from time import perf_counter
from typing import Any

from services.logger_service import ai_logger


def started_timer() -> float:
    return perf_counter()


def response_usage(response: Any) -> dict[str, int | None]:
    """Read provider usage defensively across object and dictionary responses."""

    usage = getattr(response, "usage", None)
    if usage is None and isinstance(response, dict):
        usage = response.get("usage")

    def value(*names: str) -> int | None:
        for name in names:
            candidate = usage.get(name) if isinstance(usage, dict) else getattr(usage, name, None)
            if candidate is None:
                continue
            if isinstance(candidate, bool):
                continue
            try:
                return int(candidate)
            except (TypeError, ValueError):
                continue
        return None

    return {
        "input_tokens": value("input_tokens", "prompt_tokens"),
        "output_tokens": value("output_tokens", "completion_tokens"),
        "total_tokens": value("total_tokens"),
    }


def record_llm_event(
    *,
    feature: str,
    status: str,
    provider: str | None,
    model: str | None,
    started_at: float,
    response: Any = None,
    error: Exception | None = None,
) -> None:
    """Store metadata only; narration text, prompts and client IDs never enter this log."""

    usage = response_usage(response)
    latency_ms = max(0, round((perf_counter() - started_at) * 1000))
    try:
        from database_postgres import db

        connection = db()
        cursor = connection.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO llm_observability_events (
                    feature, status, provider, model, latency_ms, input_tokens,
                    output_tokens, total_tokens, error_type
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    feature,
                    status,
                    provider,
                    model,
                    latency_ms,
                    usage["input_tokens"],
                    usage["output_tokens"],
                    usage["total_tokens"],
                    type(error).__name__ if error else None,
                ),
            )
            connection.commit()
        finally:
            cursor.close()
            connection.close()
    except Exception as log_error:
        ai_logger.warning(
            "llm_observability_write_failed feature=%s status=%s error=%s",
            feature,
            status,
            type(log_error).__name__,
        )

    ai_logger.info(
        "llm_outcome feature=%s status=%s provider=%s model=%s latency_ms=%s input_tokens=%s output_tokens=%s total_tokens=%s error_type=%s",
        feature,
        status,
        provider,
        model,
        latency_ms,
        usage["input_tokens"],
        usage["output_tokens"],
        usage["total_tokens"],
        type(error).__name__ if error else None,
    )


def list_llm_observability(*, hours: int = 24) -> list[dict[str, Any]]:
    """Return an admin-safe aggregate, not individual prompts or client records."""

    from database_postgres import db

    connection = db()
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            SELECT feature, status, provider, model, COUNT(*),
                   AVG(latency_ms), SUM(input_tokens), SUM(output_tokens),
                   SUM(total_tokens), MAX(created_at)
            FROM llm_observability_events
            WHERE created_at >= CURRENT_TIMESTAMP - (%s * INTERVAL '1 hour')
            GROUP BY feature, status, provider, model
            ORDER BY MAX(created_at) DESC
            """,
            (hours,),
        )
        return [
            {
                "feature": row[0],
                "status": row[1],
                "provider": row[2],
                "model": row[3],
                "count": row[4],
                "average_latency_ms": round(float(row[5]), 1) if row[5] is not None else None,
                "input_tokens": row[6] or 0,
                "output_tokens": row[7] or 0,
                "total_tokens": row[8] or 0,
                "last_event_at": row[9].isoformat() if row[9] else None,
            }
            for row in cursor.fetchall()
        ]
    finally:
        cursor.close()
        connection.close()
