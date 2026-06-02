from database import db


def load_fit(session_id):

    con = db()
    c = con.cursor()

    c.execute("""
        SELECT
            timestamp,
            heart_rate,
            pulse,
            hr,
            spo2,
            rr_interval,
            hrv
        FROM fit_data
        WHERE session_id=?
        ORDER BY id ASC
    """, (session_id,))

    rows = c.fetchall()
    con.close()

    return [
        {
            "timestamp": r[0],
            "time": r[0],
            "heart_rate": r[1] or r[2] or r[3],
            "pulse": r[2] or r[1] or r[3],
            "hr": r[3] or r[1] or r[2],
            "spo2": r[4],
            "rr_interval": r[5],
            "hrv": r[6],
            "source": "fit",
        }
        for r in rows
    ]


def load_csv(session_id):

    con = db()
    c = con.cursor()

    c.execute("""
        SELECT
            timestamp,
            pulse,
            heart_rate,
            spo2
        FROM csv_data
        WHERE session_id=?
        ORDER BY id ASC
    """, (session_id,))

    rows = c.fetchall()
    con.close()

    return [
        {
            "timestamp": r[0],
            "time": r[0],
            "pulse": r[1] or r[2],
            "heart_rate": r[2] or r[1],
            "spo2": r[3],
            "source": "csv",
        }
        for r in rows
    ]


def save_fit(session_id, fit_data):
    return True


def save_csv(session_id, csv_data):
    return True