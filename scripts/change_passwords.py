import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from werkzeug.security import generate_password_hash
from database_postgres import db


NEW_PASSWORDS = {
    "admin@corelabtech.local": "JP2HoLAuTcBifqMUH5Of7UMZhfz0xBFa",
    "researcher@corelabtech.local": "CJfgB1w519/THdaThvEm62wErg8liJoV",
}


con = db()
c = con.cursor()

for email, password in NEW_PASSWORDS.items():

    hashed = generate_password_hash(password)

    c.execute(
        """
        UPDATE users
        SET password_hash = %s
        WHERE email = %s
        """,
        (hashed, email)
    )

    if c.rowcount == 0:
        print(f"NOT FOUND: {email}")
    else:
        print(f"Updated password for: {email}")

con.commit()

c.close()
con.close()

print("DONE")