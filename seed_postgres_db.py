from database_postgres import db
from werkzeug.security import generate_password_hash


def seed_postgres_db():

    con = db()
    c = con.cursor()

    users = [

        {
            "user_id": "admin",
            "email": "admin@corelabtech.local",
            "subject_id": "ADMIN",
            "sex": None,
            "age": None,
            "weight": None,
            "password": "Admin123!",
            "role": "admin",
            "notes": "Default admin account"
        },

        {
            "user_id": "operator_demo",
            "email": "operator@corelabtech.local",
            "subject_id": "HBOT_DEMO_001",
            "sex": "M",
            "age": 46,
            "weight": 83,
            "password": "Operator123!",
            "role": "operator",
            "notes": "Demo operator account"
        },

        {
            "user_id": "researcher_demo",
            "email": "researcher@corelabtech.local",
            "subject_id": "RESEARCHER",
            "sex": None,
            "age": None,
            "weight": None,
            "password": "Researcher123!",
            "role": "researcher",
            "notes": "Demo researcher account"
        },

        {
            "user_id": "viewer_demo",
            "email": "viewer@corelabtech.local",
            "subject_id": "VIEWER",
            "sex": None,
            "age": None,
            "weight": None,
            "password": "Viewer123!",
            "role": "viewer",
            "notes": "Demo viewer account"
        }

    ]

    for u in users:

        c.execute("""
            INSERT INTO users (
                user_id,
                email,
                subject_id,
                sex,
                age,
                weight,
                password_hash,
                role,
                is_active,
                notes
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s
            )

            ON CONFLICT (user_id)

            DO UPDATE SET
                email = EXCLUDED.email,
                subject_id = EXCLUDED.subject_id,
                sex = EXCLUDED.sex,
                age = EXCLUDED.age,
                weight = EXCLUDED.weight,
                password_hash = EXCLUDED.password_hash,
                role = EXCLUDED.role,
                is_active = EXCLUDED.is_active,
                notes = EXCLUDED.notes

        """, (

            u["user_id"],
            u["email"],
            u["subject_id"],
            u["sex"],
            u["age"],
            u["weight"],
            generate_password_hash(u["password"]),
            u["role"],
            True,
            u["notes"]

        ))

    con.commit()

    c.close()
    con.close()

    print("========================================")
    print("PostgreSQL seed completed")
    print("========================================")

    print("Admin:")
    print("  admin@corelabtech.local / Admin123!")

    print("Operator:")
    print("  operator@corelabtech.local / Operator123!")

    print("Researcher:")
    print("  researcher@corelabtech.local / Researcher123!")

    print("Viewer:")
    print("  viewer@corelabtech.local / Viewer123!")

    print("========================================")


if __name__ == "__main__":
    seed_postgres_db()