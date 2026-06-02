from flask_login import UserMixin
from database_postgres import db


class User(UserMixin):

    def __init__(self, id, user_id, email, password_hash, role, is_active=True):
        self.id = str(id)
        self.user_id = user_id
        self.email = email
        self.password_hash = password_hash
        self.role = role or "viewer"
        self._is_active = is_active

    @property
    def is_active(self):
        return bool(self._is_active)


def row_to_user(row):

    if not row:
        return None

    return User(
        id=row[0],
        user_id=row[1],
        email=row[2],
        password_hash=row[3],
        role=row[4],
        is_active=row[5]
    )


def get_user_by_id(id):

    con = db()
    c = con.cursor()

    c.execute("""
        SELECT id, user_id, email, password_hash, role, is_active
        FROM users
        WHERE id=%s
        LIMIT 1
    """, (id,))

    row = c.fetchone()

    c.close()
    con.close()

    return row_to_user(row)


def get_user_by_email(email):

    con = db()
    c = con.cursor()

    c.execute("""
        SELECT id, user_id, email, password_hash, role, is_active
        FROM users
        WHERE email=%s
        LIMIT 1
    """, (email,))

    row = c.fetchone()

    c.close()
    con.close()

    return row_to_user(row)