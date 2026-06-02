import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()


def db():

    os.environ["PGCLIENTENCODING"] = "UTF8"

    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError("DATABASE_URL missing")

    return psycopg2.connect(
        database_url,
        client_encoding="UTF8"
    )