"""Create the Phase 6.6 audit_events table in the configured PostgreSQL database."""

from database.connection import engine
from database.models import AuditEvent


def migrate() -> None:
    AuditEvent.__table__.create(bind=engine, checkfirst=True)


if __name__ == "__main__":
    migrate()
