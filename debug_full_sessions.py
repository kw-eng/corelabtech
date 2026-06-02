import sqlite3

con = sqlite3.connect("data/database.db")
c = con.cursor()

c.execute("SELECT name FROM sqlite_master WHERE type='table'")
print("TABLES:")
for r in c.fetchall():
    print(r[0])

print("\nFULL SESSIONS:")
c.execute("""
    SELECT session_id, user_id, completed, created_at
    FROM full_sessions
    ORDER BY id DESC
    LIMIT 10
""")

rows = c.fetchall()

for r in rows:
    print(r)

print("COUNT:", len(rows))

con.close()