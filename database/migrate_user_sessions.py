import sqlite3

from database.connection import (
    migration_engine,
    MigrationSessionLocal,
    Base,
)

from database.models import UserSession

SOURCE_DATABASE = "data/auth_store.db"


def migrate_user_sessions():
    print("Creating user_sessions table...")

    # Create only the user_sessions table if it does not exist.
    Base.metadata.create_all(bind=migration_engine)

    source = sqlite3.connect(SOURCE_DATABASE)
    source.row_factory = sqlite3.Row

    db = MigrationSessionLocal()

    try:
        rows = source.execute(
            """
            SELECT
                session_id,
                phone_number,
                phone_hash,
                token_jti,
                issued_at,
                expires_at,
                revoked_at,
                last_seen_at,
                last_ip,
                last_user_agent
            FROM user_sessions
            """
        ).fetchall()

        print(f"User sessions found: {len(rows)}")

        existing = {
            row[0]
            for row in db.query(UserSession.session_id).all()
        }

        migrated = 0

        for row in rows:

            if row["session_id"] in existing:
                continue

            db.add(
                UserSession(
                    session_id=row["session_id"],
                    phone_number=row["phone_number"],
                    phone_hash=row["phone_hash"],
                    token_jti=row["token_jti"],
                    issued_at=row["issued_at"],
                    expires_at=row["expires_at"],
                    revoked_at=row["revoked_at"],
                    last_seen_at=row["last_seen_at"],
                    last_ip=row["last_ip"],
                    last_user_agent=row["last_user_agent"],
                )
            )

            migrated += 1

        db.commit()

        print(f"User sessions migrated: {migrated}")

        print("\n========================================")
        print("USER SESSION MIGRATION SUCCESSFUL")
        print("========================================")

    except Exception:
        db.rollback()

        print("\nUSER SESSION MIGRATION FAILED.")

        raise

    finally:
        source.close()
        db.close()


if __name__ == "__main__":
    migrate_user_sessions()