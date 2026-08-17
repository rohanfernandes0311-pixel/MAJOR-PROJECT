import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL must be configured for PostgreSQL/Neon runtime persistence")

# Keep connection options centralized for the PostgreSQL runtime engine.
connect_args = {}

if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgresql://",
        "postgresql+psycopg://",
        1,
    )

if not DATABASE_URL.startswith("postgresql+"):
    raise RuntimeError("DATABASE_URL must target PostgreSQL/Neon; SQLite is migration-only")

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
