"""
NAVISCAPE Database Configuration
SQLAlchemy engine and session management with SQLite WAL mode.
Includes additive schema migration for the authentication rebuild.
"""

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import settings

# Normalize DATABASE_URL
db_url = settings.DATABASE_URL
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
elif db_url.startswith("libsql://"):
    db_url = db_url.replace("libsql://", "sqlite+libsql://", 1)

is_turso = "libsql" in db_url
is_sqlite = db_url.startswith("sqlite") and not is_turso

# Create engine with dialect-specific settings
if is_turso:
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
        echo=settings.DEBUG,
    )
elif is_sqlite:
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},  # Required for SQLite + FastAPI
        echo=settings.DEBUG,
    )

    # Enable WAL mode for better concurrent read/write performance on local SQLite
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
else:
    # PostgreSQL (Supabase, Neon, etc.)
    connect_args = {}
    if "sslmode" not in db_url:
        connect_args["sslmode"] = "require"

    engine = create_engine(
        db_url,
        connect_args=connect_args,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        echo=settings.DEBUG,
    )


# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for ORM models
Base = declarative_base()

_db_initialized = False


def get_db():
    """FastAPI dependency that provides a database session per request."""
    global _db_initialized
    if not _db_initialized:
        try:
            init_db()
            _db_initialized = True
        except Exception as exc:
            print(f"[DB LAZY INIT WARNING]: {exc}")

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


def _migrate_traffic_table():
    """
    Additive migration for the traffic_data table.
    Checks for the existence of is_test, free_flow_speed, and speed_ratio columns,
    and runs ALTER TABLE statements to add them if missing.
    """
    new_columns = {
        "is_test": "BOOLEAN DEFAULT 0",
        "free_flow_speed": "FLOAT",
        "speed_ratio": "FLOAT",
    }
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("PRAGMA table_info(traffic_data)")).fetchall()
            if not rows:
                return
            existing_cols = {row[1] for row in rows}

            for col_name, col_def in new_columns.items():
                if col_name not in existing_cols:
                    conn.execute(text(f"ALTER TABLE traffic_data ADD COLUMN {col_name} {col_def}"))
                    print(f"[MIGRATE] traffic_data: added column '{col_name}'")

            conn.commit()
    except Exception as exc:
        print(f"[MIGRATE] traffic_data migration warning: {exc}")


def _migrate_traffic_unique_index():
    """
    Safely creates a composite unique index on traffic_data(junction_id, timestamp).
    Pre-checks for existing duplicates before creating the index.
    If duplicates exist: reports them and halts index creation without modifying any data.
    """
    try:
        with engine.connect() as conn:
            table_check = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='traffic_data'")).fetchone()
            if not table_check:
                return

            # Pre-check for duplicate (junction_id, timestamp) pairs
            dup_query = text("""
                SELECT junction_id, timestamp, COUNT(*) as count
                FROM traffic_data
                GROUP BY junction_id, timestamp
                HAVING COUNT(*) > 1
            """)
            dup_rows = conn.execute(dup_query).fetchall()
            if dup_rows:
                dup_details = [(row[0], str(row[1]), row[2]) for row in dup_rows]
                msg = f"[MIGRATE ERROR] Found {len(dup_rows)} duplicate (junction_id, timestamp) pairs in traffic_data: {dup_details}. Halting unique index creation without modifying records."
                print(msg)
                raise RuntimeError(msg)

            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_traffic_junction_timestamp ON traffic_data (junction_id, timestamp)"))
            conn.commit()
            print("[MIGRATE] traffic_data: verified uniqueness and ensured unique index 'uq_traffic_junction_timestamp'")
    except RuntimeError:
        raise
    except Exception as exc:
        print(f"[MIGRATE] traffic_data unique index migration warning: {exc}")


def _migrate_traffic_hourly_table():
    """
    Ensures traffic_hourly composite unique index exists with pre-check safeguard.
    If duplicates exist: reports them and halts index creation without modifying records.
    """
    try:
        with engine.connect() as conn:
            table_check = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='traffic_hourly'")).fetchone()
            if not table_check:
                return

            # Pre-check for duplicate (junction_id, timestamp, is_test) pairs
            dup_query = text("""
                SELECT junction_id, timestamp, is_test, COUNT(*) as count
                FROM traffic_hourly
                GROUP BY junction_id, timestamp, is_test
                HAVING COUNT(*) > 1
            """)
            dup_rows = conn.execute(dup_query).fetchall()
            if dup_rows:
                dup_details = [(row[0], str(row[1]), row[2], row[3]) for row in dup_rows]
                msg = f"[MIGRATE ERROR] Found {len(dup_rows)} duplicate (junction_id, timestamp, is_test) pairs in traffic_hourly: {dup_details}. Halting unique index creation without modifying records."
                print(msg)
                raise RuntimeError(msg)

            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_traffic_hourly_junction_time_test ON traffic_hourly (junction_id, timestamp, is_test)"))
            conn.commit()
            print("[MIGRATE] traffic_hourly: verified uniqueness and ensured unique index 'uq_traffic_hourly_junction_time_test'")
    except RuntimeError:
        raise
    except Exception as exc:
        print(f"[MIGRATE] traffic_hourly migration warning: {exc}")


def _migrate_trusted_contacts_whatsapp():
    """
    WS-3A: Additive migration for trusted_contacts table.
    Adds whatsapp_number (nullable TEXT) and whatsapp_alert_consent (BOOLEAN DEFAULT 0)
    columns if they do not already exist. Idempotent — safe to run on every startup.
    Existing rows get NULL for whatsapp_number and 0 (False) for whatsapp_alert_consent.
    """
    new_columns = {
        "whatsapp_number": "VARCHAR(20)",
        "whatsapp_alert_consent": "BOOLEAN NOT NULL DEFAULT 0",
    }
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("PRAGMA table_info(trusted_contacts)")).fetchall()
            if not rows:
                return
            existing_cols = {row[1] for row in rows}

            for col_name, col_def in new_columns.items():
                if col_name not in existing_cols:
                    conn.execute(text(f"ALTER TABLE trusted_contacts ADD COLUMN {col_name} {col_def}"))
                    print(f"[MIGRATE] trusted_contacts: added column '{col_name}'")

            conn.commit()
    except Exception as exc:
        print(f"[MIGRATE] trusted_contacts WhatsApp migration warning: {exc}")


def init_db():
    """Create all tables and run additive migrations. Called on application startup."""
    # Register all models so Base.metadata knows about them
    from .models import user, traffic, accident, road_hazard  # noqa: F401
    from .models import otp  # noqa: F401
    from .models import police_station  # noqa: F401
    from .models import hospital  # noqa: F401
    from .models import emergency_profile  # noqa: F401
    from .models import emergency_event  # noqa: F401

    # Run SQLite-specific migrations only when using SQLite
    if is_sqlite:
        _migrate_accident_table()
        _migrate_users_table()
        _migrate_traffic_table()
        _migrate_traffic_unique_index()
        _migrate_trusted_contacts_whatsapp()

    # create_all creates all tables/columns if they don't exist
    Base.metadata.create_all(bind=engine)

    if is_sqlite:
        # Ensure unique index on newly created traffic_hourly table
        _migrate_traffic_hourly_table()
