CLIENT_STAFF_ROLES = frozenset({"admin", "researcher", "operator"})


def can_access_client_record(
    *,
    requesting_role: str,
    requesting_user_id: str | None,
    client_id: str | None,
    requesting_organization_id: int | None = None,
) -> bool:
    """Return whether the current account may access one client's record."""

    if requesting_role == "admin":
        return True

    if requesting_role in CLIENT_STAFF_ROLES:
        if requesting_organization_id is None:
            return True

        from database_postgres import db

        connection = db()
        cursor = connection.cursor()
        try:
            cursor.execute(
                """
                SELECT organization_id
                FROM users
                WHERE user_id = %s
                LIMIT 1
                """,
                (client_id,),
            )
            row = cursor.fetchone()
            return bool(
                row
                and row[0] is not None
                and int(row[0]) == int(requesting_organization_id)
            )
        finally:
            cursor.close()
            connection.close()

    return bool(
        requesting_user_id
        and client_id
        and requesting_user_id == client_id
    )
