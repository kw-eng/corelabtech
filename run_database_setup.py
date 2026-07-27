from __future__ import annotations

import importlib.util
import os
import hashlib
import sys
from pathlib import Path
from types import ModuleType

from database_postgres import db


ROOT = Path(__file__).resolve().parent

BASE_SETUP = ROOT / "init_postgres_db.py"

MIGRATIONS = [
    ROOT / "migrations" / "004_create_csv_imports.py",
    ROOT / "migrations" / "005_extend_csv_data.py",
    ROOT / "migrations" / "006_create_fit_imports.py",
    ROOT / "migrations" / "007_extend_fit_data.py",
    ROOT / "migrations" / "008_create_merge_jobs.py",
    ROOT / "migrations" / "009_create_merged_data.py",
    ROOT / "migrations" / "010_create_ai_results.py",
    ROOT / "migrations" / "011_create_hrv_tables.py",
    ROOT / "migrations" / "012_create_session_features_baselines.py",
    ROOT / "migrations" / "014_create_chambers_protocols.py",
    ROOT / "migrations" / "013_repair_client_ownership.py",
    ROOT / "migrations" / "015_create_data_governance.py",
    ROOT / "migrations" / "016_add_session_phase_timing.py",
    ROOT / "migrations" / "017_add_commercial_wellness_model.py",
]


def main() -> int:
    print("CoreLabTech database setup")
    print("=" * 32)

    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        print("ERROR: DATABASE_URL is not set.")
        print(
            "Example: "
            "$env:DATABASE_URL="
            "'postgresql://user:password@localhost:5432/corelabtech'"
        )
        return 1

    try:
        run_base_setup()
        run_migrations()
    except Exception as exc:
        print()
        print("DATABASE SETUP FAILED")
        print(f"{type(exc).__name__}: {exc}")
        return 1

    print()
    print("DATABASE SETUP COMPLETED")
    return 0


def run_base_setup() -> None:
    print()
    print("[base] init_postgres_db.py")

    module = load_module(BASE_SETUP)

    if hasattr(module, "init_postgres_db"):
        module.init_postgres_db()
    elif hasattr(module, "init_db"):
        module.init_db()
    elif hasattr(module, "upgrade"):
        module.upgrade()
    elif hasattr(module, "main"):
        module.main()
    else:
        raise RuntimeError(
            "init_postgres_db.py must expose "
            "init_postgres_db(), init_db(), upgrade(), or main()"
        )

    print("[ok] base schema")


def run_migrations() -> None:
    print()
    print("[migrations]")

    ensure_schema_migrations()

    for migration in MIGRATIONS:
        version = migration.stem
        checksum = file_checksum(migration)

        if migration_already_applied(version):
            print(f"- {migration.relative_to(ROOT)} [skip]")
            continue

        print(f"- {migration.relative_to(ROOT)}")
        module = load_module(migration)

        if not hasattr(module, "upgrade"):
            raise RuntimeError(
                f"{migration.name} does not expose upgrade()"
            )

        module.upgrade()
        record_migration(
            version=version,
            filename=str(migration.relative_to(ROOT)),
            checksum=checksum,
        )
        print(f"  [ok] {migration.name}")


def ensure_schema_migrations() -> None:
    connection = db()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version VARCHAR(255) PRIMARY KEY,
                filename TEXT NOT NULL,
                checksum VARCHAR(64) NOT NULL,
                applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()


def migration_already_applied(version: str) -> bool:
    connection = db()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT 1
            FROM schema_migrations
            WHERE version = %s
            LIMIT 1
            """,
            (version,),
        )
        return cursor.fetchone() is not None

    finally:
        cursor.close()
        connection.close()


def record_migration(
    *,
    version: str,
    filename: str,
    checksum: str,
) -> None:
    connection = db()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO schema_migrations (
                version,
                filename,
                checksum
            )
            VALUES (%s, %s, %s)
            ON CONFLICT (version)
            DO UPDATE SET
                filename = EXCLUDED.filename,
                checksum = EXCLUDED.checksum
            """,
            (
                version,
                filename,
                checksum,
            ),
        )
        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()


def file_checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_module(path: Path) -> ModuleType:
    if not path.exists():
        raise FileNotFoundError(path)

    module_name = (
        "corelabtech_setup_"
        + path.stem
        + "_"
        + str(abs(hash(path)))
    )

    spec = importlib.util.spec_from_file_location(
        module_name,
        path,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module from {path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module


if __name__ == "__main__":
    sys.exit(main())
