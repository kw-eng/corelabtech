from database_postgres import db


def check_postgres_db():

    con = db()
    c = con.cursor()

    tables = [
        "users",
        "tests",
        "fit_data",
        "csv_data",
        "full_sessions"
    ]

    print("PostgreSQL table counts:")
    print("-" * 40)

    for table in tables:

        c.execute(f"SELECT COUNT(*) FROM {table}")
        count = c.fetchone()[0]

        print(f"{table}: {count}")

    print("-" * 40)
    print("PostgreSQL check completed.")

    c.close()
    con.close()


if __name__ == "__main__":
    check_postgres_db()