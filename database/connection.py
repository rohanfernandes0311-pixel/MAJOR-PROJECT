import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


# ---------------------------------------------------------
# Database URL
# ---------------------------------------------------------
# Local development:
#     SQLite database
#
# Production:
#     Set DATABASE_URL to your PostgreSQL connection string
#
# Example:
#     postgresql+psycopg://username:password@host:5432/landsense
# ---------------------------------------------------------

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./data/landsense_unified.db"
)

# SQLite requires this option when used with FastAPI
# because multiple requests may use the database connection.
connect_args = {}

if DATABASE_URL.startswith("sqlite"):
    connect_args = {
        "check_same_thread": False
    }


# ---------------------------------------------------------
# SQLAlchemy Engine
# ---------------------------------------------------------

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
)


# ---------------------------------------------------------
# Database Session
# ---------------------------------------------------------

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


# ---------------------------------------------------------
# Base class for future database models
# ---------------------------------------------------------

class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------
# FastAPI database dependency
# ---------------------------------------------------------

def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()
        # ---------------------------------------------------------
# Migration target database
# ---------------------------------------------------------

MIGRATION_DATABASE_URL = "sqlite:///./data/landsense_unified.db"

migration_engine = create_engine(
    MIGRATION_DATABASE_URL,
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
)

MigrationSessionLocal = sessionmaker(
    bind=migration_engine,
    autoflush=False,
    autocommit=False,
)