"""Idempotently create the PostgreSQL dataset-backed landslide inventory table.

Run after DATABASE_URL is configured:
    python -m database.migrate_add_landslide_inventory
"""

from sqlalchemy import inspect

from database.connection import engine
from database.models import LandslideInventory


def migrate() -> dict[str, object]:
    if engine.dialect.name != "postgresql":
        raise RuntimeError("This migration is PostgreSQL/Neon-only; DATABASE_URL must target Neon.")

    with engine.begin() as connection:
        existed = inspect(connection).has_table(LandslideInventory.__tablename__)
        LandslideInventory.__table__.create(bind=connection, checkfirst=True)
        exists_after = inspect(connection).has_table(LandslideInventory.__tablename__)

    return {
        "table": LandslideInventory.__tablename__,
        "created": not existed and exists_after,
        "already_present": existed,
    }


if __name__ == "__main__":
    print(migrate())
