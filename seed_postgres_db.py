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
            "password": "CHANGE_ME_ADMIN_PASSWORD",
            "role": "admin",
            "notes": "Default admin account"
        },

        {
            "user_id": "researcher_demo",
            "email": "researcher@corelabtech.local",
            "subject_id": "RESEARCHER",
            "sex": None,
            "age": None,
            "weight": None,
            "password": "CHANGE_ME_RESEARCHER_PASSWORD",
            "role": "researcher",
            "notes": "Demo researcher account"
        },

        # Enable only for local testing if needed.
        # {
        #     "user_id": "operator_demo",
        #     "email": "operator@corelabtech.local",
        #     "subject_id": "HBOT_DEMO_001",
        #     "sex": "M",
        #     "age": 46,
        #     "weight": 83,
        #     "password": "CHANGE_ME_OPERATOR_PASSWORD",
        #     "role": "operator",
        #     "notes": "Demo operator account"
        # },

        # Enable only for local testing if needed.
        # {
        #     "user_id": "viewer_demo",
        #     "email": "viewer@corelabtech.local",
        #     "subject_id": "VIEWER",
        #     "sex": None,
        #     "age": None,
        #     "weight": None,
        #     "password": "CHANGE_ME_VIEWER_PASSWORD",
        #     "role": "viewer",
        #     "notes": "Demo viewer account"
        # }

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

    print("Active production/demo accounts:")
    print("  admin@corelabtech.local / CHANGE_ME_ADMIN_PASSWORD")
    print("  researcher@corelabtech.local / CHANGE_ME_RESEARCHER_PASSWORD")

    print("")
    print("Operator/viewer examples are commented out in seed_postgres_db.py")
    print("Enable them only for local testing if needed.")

    print("========================================")


if __name__ == "__main__":
    seed_postgres_db()