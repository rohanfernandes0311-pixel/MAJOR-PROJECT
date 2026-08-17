"""Idempotent PostgreSQL/Neon migration for the persisted User.role field.

Run from the project directory after DATABASE_URL is configured:
    .venv\\Scripts\\python -m database.migrate_add_user_role
"""

from sqlalchemy import inspect, text

from database.connection import engine


def migrate() -> dict[str, int]:
    """Add and backfill users.role without recreating any table."""
    if engine.dialect.name != "postgresql":
        raise RuntimeError("This migration is PostgreSQL/Neon-only; DATABASE_URL must target Neon.")

    with engine.begin() as connection:
        before_count = int(connection.scalar(text("SELECT count(*) FROM users")) or 0)
        columns = {column["name"] for column in inspect(connection).get_columns("users")}

        if "role" not in columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR(32)"))

        backfilled = connection.execute(
            text("UPDATE users SET role = 'Citizen' WHERE role IS NULL OR btrim(role) = ''")
        ).rowcount
        connection.execute(text("ALTER TABLE users ALTER COLUMN role SET DEFAULT 'Citizen'"))
        connection.execute(text("ALTER TABLE users ALTER COLUMN role SET NOT NULL"))

        after_count = int(connection.scalar(text("SELECT count(*) FROM users")) or 0)
        if before_count != after_count:
            raise RuntimeError("Safety check failed: users row count changed during migration")

    return {"users_before": before_count, "users_after": after_count, "rows_defaulted": int(backfilled or 0)}


if __name__ == "__main__":
    print(migrate())
