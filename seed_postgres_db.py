from database_postgres import db
from datetime import datetime, timedelta
import os
import json
from werkzeug.security import generate_password_hash


def seed_postgres_db():

    admin_password = os.getenv(
        "E2E_ADMIN_PASSWORD",
        "CHANGE_ME_ADMIN_PASSWORD"
    )

    researcher_password = os.getenv(
        "E2E_RESEARCHER_PASSWORD",
        "CHANGE_ME_RESEARCHER_PASSWORD"
    )

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
            "password": admin_password,
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
            "password": researcher_password,
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

    seed_contract_session(c)

    con.commit()

    c.close()
    con.close()

    print("========================================")
    print("PostgreSQL seed completed")
    print("========================================")

    print("Active production/demo accounts:")
    print("  admin@corelabtech.local / configured from E2E_ADMIN_PASSWORD")
    print("  researcher@corelabtech.local / configured from E2E_RESEARCHER_PASSWORD")

    print("")
    print("Operator/viewer examples are commented out in seed_postgres_db.py")
    print("Enable them only for local testing if needed.")

    print("========================================")


def seed_contract_session(cursor):
    session_id = "E2E_CONTRACT_SESSION"
    user_id = "E2E_CONTRACT_USER"
    now = datetime.utcnow().replace(microsecond=0)

    cursor.execute(
        """
        INSERT INTO users (
            user_id,
            email,
            subject_id,
            role,
            is_active,
            notes
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (user_id)
        DO UPDATE SET
            subject_id = EXCLUDED.subject_id,
            role = EXCLUDED.role,
            is_active = EXCLUDED.is_active,
            notes = EXCLUDED.notes
        """,
        (
            user_id,
            None,
            user_id,
            "operator",
            True,
            "E2E contract fixture subject",
        ),
    )

    pre = {
        "saved": True,
        "phase": "pre",
        "spo2": 98,
        "pulse": 64,
    }

    during = {
        "saved": True,
        "phase": "during",
        "source": "seed_postgres_db",
    }

    post = {
        "saved": True,
        "phase": "post",
        "spo2": 98,
        "pulse": 66,
    }

    cursor.execute(
        """
        INSERT INTO full_sessions (
            session_id,
            user_id,
            session_status,
            pre_json,
            during_json,
            post_json,
            summary,
            completed
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (session_id)
        DO UPDATE SET
            user_id = EXCLUDED.user_id,
            session_status = EXCLUDED.session_status,
            pre_json = EXCLUDED.pre_json,
            during_json = EXCLUDED.during_json,
            post_json = EXCLUDED.post_json,
            summary = EXCLUDED.summary,
            completed = EXCLUDED.completed
        """,
        (
            session_id,
            user_id,
            "completed",
            json.dumps(pre),
            json.dumps(during),
            json.dumps(post),
            json.dumps({
                "source": "seed_postgres_db",
                "purpose": "E2E AI contract fixture",
            }),
            1,
        ),
    )

    cursor.execute(
        "DELETE FROM merge_jobs WHERE session_id = %s",
        (session_id,),
    )

    cursor.execute(
        """
        INSERT INTO merge_jobs (
            session_id,
            user_id,
            fit_records,
            csv_records,
            merged_records,
            algorithm,
            tolerance_ms,
            status,
            finished_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
        RETURNING merge_id
        """,
        (
            session_id,
            user_id,
            5,
            5,
            5,
            "seeded_e2e_fixture",
            2500,
            "COMPLETED",
        ),
    )

    merge_id = cursor.fetchone()[0]

    for index in range(5):
        timestamp = now + timedelta(seconds=index * 30)

        cursor.execute(
            """
            INSERT INTO merged_data (
                merge_id,
                session_id,
                user_id,
                timestamp,
                phase,
                heart_rate,
                hrv,
                rr_interval,
                spo2,
                pulse,
                fit_timestamp,
                csv_timestamp,
                delta_ms,
                synchronized,
                status
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s
            )
            """,
            (
                merge_id,
                session_id,
                user_id,
                timestamp,
                "during",
                72 + index,
                48 + index,
                820 + index,
                98,
                71 + index,
                timestamp,
                timestamp,
                0,
                True,
                "SYNCED",
            ),
        )


if __name__ == "__main__":
    seed_postgres_db()
