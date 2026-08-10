"""
NAVISCAPE Database Configuration
SQLAlchemy engine and session management with SQLite WAL mode.
"""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import settings

# Create engine with SQLite-specific settings
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False},  # Required for SQLite + FastAPI
    echo=settings.DEBUG,
)


# Enable WAL mode for better concurrent read/write performance
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for ORM models
Base = declarative_base()


def get_db():
    """FastAPI dependency that provides a database session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables. Called on application startup."""
    from .models import user, traffic, accident  # noqa: F401 — import to register models

    # Schema migration: drop old skeleton accident_data if it lacks the 'district' column
    # (safe — old table was never populated with real data)
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            cols = [row[1] for row in conn.execute(text("PRAGMA table_info(accident_data)"))]
            if cols and "district" not in cols:
                conn.execute(text("DROP TABLE IF EXISTS accident_data"))
                conn.commit()
                print("[MIGRATE] Dropped legacy accident_data schema — rebuilding with Karnataka dataset schema.")
    except Exception:
        pass

    Base.metadata.create_all(bind=engine)
