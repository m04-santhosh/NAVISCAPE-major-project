"""
NAVISCAPE Database Configuration
SQLAlchemy engine and session management with SQLite WAL mode.
Includes additive schema migration for the authentication rebuild.
"""

from sqlalchemy import create_engine, event, text
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


def _migrate_users_table():
    """
    Additive migration for the users table.

    Strategy: detect existing columns via PRAGMA table_info, then ALTER TABLE
    to add any new columns that are missing. Legacy columns (username,
    hashed_password, full_name, is_admin) are LEFT IN PLACE so existing
    route_history foreign keys remain valid and no data is lost.

    This function is idempotent — safe to run on every startup.
    """
    new_columns = {
        "email_verified": "BOOLEAN NOT NULL DEFAULT 0",
        "pin_hash":       "TEXT",
        "updated_at":     "DATETIME",
        "last_login_at":  "DATETIME",
    }
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("PRAGMA table_info(users)")).fetchall()
            if not rows:
                # Table doesn't exist yet — create_all will handle it
                return
            existing_cols = {row[1] for row in rows}  # row[1] = column name

            for col_name, col_def in new_columns.items():
                if col_name not in existing_cols:
                    conn.execute(text(f"ALTER TABLE users ADD COLUMN {col_name} {col_def}"))
                    print(f"[MIGRATE] users: added column '{col_name}'")

            conn.commit()
    except Exception as exc:
        print(f"[MIGRATE] users migration warning: {exc}")


def _migrate_accident_table():
    """
    Drop legacy accident_data table if it lacks the 'district' column.
    (Safe — old table was never populated with real data.)
    """
    try:
        with engine.connect() as conn:
            cols = [row[1] for row in conn.execute(text("PRAGMA table_info(accident_data)"))]
            if cols and "district" not in cols:
                conn.execute(text("DROP TABLE IF EXISTS accident_data"))
                conn.commit()
                print("[MIGRATE] Dropped legacy accident_data schema — rebuilding with Karnataka dataset schema.")
    except Exception:
        pass


def init_db():
    """Create all tables and run additive migrations. Called on application startup."""
    # Register all models so Base.metadata knows about them
    from .models import user, traffic, accident  # noqa: F401
    from .models import otp  # noqa: F401

    # Run migrations BEFORE create_all so the table structure is correct
    _migrate_accident_table()
    _migrate_users_table()

    # create_all is safe — it only creates tables/columns that don't exist
    Base.metadata.create_all(bind=engine)
