import sqlite3

con = sqlite3.connect("data/database.db")
c = con.cursor()

c.execute("PRAGMA table_info(tests)")
print(c.fetchall())