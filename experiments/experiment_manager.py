from database import db
import datetime

def start_experiment(name):

    con = db()
    c = con.cursor()

    date = str(datetime.datetime.now())

    c.execute("""
    INSERT INTO experiments(name,date)
    VALUES(?,?)
    """,(name,date))

    con.commit()

def list_experiments():

    con = db()
    c = con.cursor()

    c.execute("SELECT id,name,date FROM experiments")

    return c.fetchall()