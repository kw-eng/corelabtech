import sqlite3
import datetime
import random

DB_PATH = "data/database.db"

con = sqlite3.connect(DB_PATH)
c = con.cursor()

# ================= USER =================
subject_id = "TEST_001"

try:
    c.execute("""
        INSERT INTO users(subject_id, sex, age, weight, notes)
        VALUES(?,?,?,?,?)
    """, (subject_id, "M", 30, 80, "seed user"))
    print("User created")
except sqlite3.IntegrityError:
    print("User already exists")

# pobierz user_id
user_id = c.execute("""
    SELECT user_id FROM users WHERE subject_id=?
""", (subject_id,)).fetchone()[0]

# ================= SESSION =================
session_id = f"{user_id}_SEED_001"

now = datetime.datetime.now()

#=====Dane PRE i POST=======
c.execute("""
INSERT INTO tests(user_id, session_id, phase, device, spo2, pulse, timestamp)
VALUES(?,?,?,?,?,?,?)
""", (user_id, session_id, "pre", "pulseox", 97, 70, now.isoformat()))

c.execute("""
INSERT INTO tests(user_id, session_id, phase, device, spo2, pulse, timestamp)
VALUES(?,?,?,?,?,?,?)
""", (user_id, session_id, "post", "pulseox", 98, 65, (now + datetime.timedelta(minutes=40)).isoformat()))
# ================= TEST DATA =================
for i in range(50):

    timestamp = (now + datetime.timedelta(seconds=i*30)).isoformat()

    spo2 = random.randint(92, 99)
    pulse = random.randint(60, 110)
    hrv = random.randint(20, 90)

    c.execute("""
    INSERT INTO tests(
        user_id,
        session_id,
        phase,
        device,
        spo2,
        pulse,
        hrv,
        pressure_ata,
        timestamp
    )
    VALUES(?,?,?,?,?,?,?,?,?)
    """, (
        user_id,
        session_id,
        "during",
        "garmin",
        spo2,
        pulse,
        hrv,
        1.4,
        timestamp
    ))

con.commit()
con.close()

print("SEED OK")