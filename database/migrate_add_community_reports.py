"""Idempotently create the additive community reporting tables.

Run manually after DATABASE_URL is configured:
    python -m database.migrate_add_community_reports

This migration never alters or recreates existing tables or records.
"""

from sqlalchemy import inspect, text

from database.connection import engine
from database.models import CommunityReport, CommunityReportReview


def migrate() -> dict[str, object]:
    if engine.dialect.name != "postgresql":
        raise RuntimeError("This migration is PostgreSQL/Neon-only; DATABASE_URL must target Neon.")

    tables = (CommunityReport, CommunityReportReview)
    result: dict[str, object] = {}
    with engine.begin() as connection:
        for model in tables:
            table = model.__table__
            existed = inspect(connection).has_table(table.name)
            table.create(bind=connection, checkfirst=True)
            result[table.name] = {"created": not existed, "already_present": existed}
        # Additive metadata fields for existing installations. These columns
        # remain nullable so pre-existing report rows need no backfill.
        connection.execute(text(
            "ALTER TABLE community_reports ADD COLUMN IF NOT EXISTS reporter_id VARCHAR(255)"
        ))
        connection.execute(text(
            "ALTER TABLE community_reports ADD COLUMN IF NOT EXISTS reporter_role VARCHAR(16) DEFAULT 'citizen'"
        ))
        connection.execute(text(
            "ALTER TABLE community_reports ADD COLUMN IF NOT EXISTS place_name VARCHAR(250)"
        ))
    return result


if __name__ == "__main__":
    print(migrate())
