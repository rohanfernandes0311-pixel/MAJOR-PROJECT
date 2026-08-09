from __future__ import annotations

import sqlite3
from pathlib import Path

from sqlalchemy import text

from database.connection import SessionLocal


BASE_DIR = Path(__file__).resolve().parents[1]
SQLITE_DB = BASE_DIR / "data" / "landsense_unified.db"


TABLES = [
    "users",
    "locations",
    "alerts",
    "location_events",
    "otp_sessions",
    "user_sessions",
    "login_history",
]


def migrate():
    if not SQLITE_DB.exists():
        raise FileNotFoundError(f"SQLite database not found: {SQLITE_DB}")

    sqlite = sqlite3.connect(SQLITE_DB)
    sqlite.row_factory = sqlite3.Row

    db = SessionLocal()

    try:
        print("=" * 50)
        print("LANDSENSE SQLITE → NEON MIGRATION")
        print("=" * 50)
        print(f"Source: {SQLITE_DB}")

        # -------------------------------------------------
        # Verify source counts
        # -------------------------------------------------

        source_counts = {}

        print("\nSOURCE COUNTS:")

        for table in TABLES:
            count = sqlite.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]

            source_counts[table] = count
            print(f"{table}: {count}")

        # -------------------------------------------------
        # Migration
        # -------------------------------------------------

        for table in TABLES:
            print(f"\nMigrating {table}...")

            rows = sqlite.execute(
                f"SELECT * FROM {table}"
            ).fetchall()

            if not rows:
                print("  No rows to migrate.")
                continue

            columns = rows[0].keys()

            column_sql = ", ".join(f'"{c}"' for c in columns)
            value_sql = ", ".join(f":{c}" for c in columns)

            insert_sql = text(
                f'INSERT INTO "{table}" ({column_sql}) '
                f"VALUES ({value_sql})"
            )

            inserted = 0

            for row in rows:
                db.execute(
                    insert_sql,
                    dict(row),
                )
                inserted += 1

            print(f"  Inserted: {inserted}")

        # -------------------------------------------------
        # Commit
        # -------------------------------------------------

        db.commit()

        print("\n========================================")
        print("MIGRATION COMMITTED")
        print("========================================")

        # -------------------------------------------------
        # Verify destination
        # -------------------------------------------------

        print("\nDESTINATION COUNTS:")

        destination_counts = {}

        for table in TABLES:
            count = db.execute(
                text(f'SELECT COUNT(*) FROM "{table}"')
            ).scalar_one()

            destination_counts[table] = count

            print(f"{table}: {count}")

        # -------------------------------------------------
        # Compare
        # -------------------------------------------------

        print("\nVERIFICATION:")

        failed = False

        for table in TABLES:
            source = source_counts[table]
            destination = destination_counts[table]

            if source == destination:
                print(f"{table}: OK ({source})")
            else:
                print(
                    f"{table}: FAILED "
                    f"(source={source}, destination={destination})"
                )
                failed = True

        if failed:
            raise RuntimeError(
                "Migration verification failed."
            )

        print("\n========================================")
        print("MIGRATION SUCCESSFUL")
        print("ALL COUNTS MATCH")
        print("========================================")

    except Exception:
        db.rollback()
        print("\nMIGRATION FAILED.")
        print("Neon transaction rolled back.")
        raise

    finally:
        db.close()
        sqlite.close()


if __name__ == "__main__":
    migrate()
    