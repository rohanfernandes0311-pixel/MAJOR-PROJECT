import os
import logging
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL must be configured for PostgreSQL/Neon runtime persistence")

# Keep connection options centralized for the PostgreSQL runtime engine.  The
# timeout applies to establishing a connection; it does not weaken Neon TLS or
# alter URL options such as sslmode/channel_binding.
CONNECT_TIMEOUT_SECONDS = 10
connect_args = {"connect_timeout": CONNECT_TIMEOUT_SECONDS}

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
    pool_recycle=300,
    pool_size=5,
    max_overflow=10,
)

logger.info(
    "Database configured: host=%s database=%s pooler=%s",
    engine.url.host or "unknown",
    engine.url.database or "unknown",
    bool(engine.url.host and "-pooler" in engine.url.host),
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
