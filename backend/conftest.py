"""
NAVISCAPE Test Isolation Conftest
Ensures that all automated test runs execute against an isolated temporary SQLite database,
preventing any test users, route history, or simulated traffic data from modifying the real
backend/naviscape.db.
"""

import os
import sys
import sqlite3
import tempfile
import atexit

# Ensure backend directory is in sys.path
_current_dir = os.path.dirname(os.path.abspath(__file__))
_backend_dir = os.path.join(_current_dir, "backend") if os.path.exists(os.path.join(_current_dir, "backend")) else _current_dir
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

_real_db_path = os.path.join(_backend_dir, "naviscape.db")

# Only initialize once if running in nested conftest hierarchies
if "naviscape_pytest_isolated" not in os.environ.get("DATABASE_URL", ""):
    # Create a unique temporary isolated database path
    _isolated_db_path = os.path.join(
        tempfile.gettempdir(),
        f"naviscape_pytest_isolated_{os.getpid()}.db"
    )

    # Remove any stale test db file from previous runs
    for _ext in ["", "-wal", "-shm"]:
        _p = _isolated_db_path + _ext
        if os.path.exists(_p):
            try:
                os.remove(_p)
            except Exception:
                pass

    # Copy existing dataset (accidents, hospitals, police, traffic schemas) using SQLite online backup API
    if os.path.exists(_real_db_path):
        _src = sqlite3.connect(_real_db_path)
        _dst = sqlite3.connect(_isolated_db_path)
        _src.backup(_dst)
        _dst.close()
        _src.close()

    # Format URI for SQLite/SQLAlchemy
    _norm_isolated_path = _isolated_db_path.replace("\\", "/")
    os.environ["DATABASE_URL"] = f"sqlite:///{_norm_isolated_path}"

    # Force app settings and SQLAlchemy engine to use the isolated database URI
    try:
        from app.config import settings
        settings.DATABASE_URL = f"sqlite:///{_norm_isolated_path}"
        
        import app.database
        from sqlalchemy import create_engine, event
        test_engine = create_engine(
            f"sqlite:///{_norm_isolated_path}",
            connect_args={"check_same_thread": False},
        )
        @event.listens_for(test_engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        app.database.engine = test_engine
        app.database.SessionLocal.configure(bind=test_engine)
        app.database.init_db()
    except Exception as _exc:
        pass


def pytest_sessionfinish(session, exitstatus):
    """Clean up the isolated test database upon test session completion."""
    try:
        from app.database import engine
        engine.dispose()
    except Exception:
        pass

    db_url = os.environ.get("DATABASE_URL", "")
    if "naviscape_pytest_isolated" in db_url:
        path = db_url.replace("sqlite:///", "")
        for _ext in ["", "-wal", "-shm"]:
            _p = path + _ext
            if os.path.exists(_p):
                try:
                    os.remove(_p)
                except Exception:
                    pass


@atexit.register
def _emergency_cleanup():
    db_url = os.environ.get("DATABASE_URL", "")
    if "naviscape_pytest_isolated" in db_url:
        path = db_url.replace("sqlite:///", "")
        for _ext in ["", "-wal", "-shm"]:
            _p = path + _ext
            if os.path.exists(_p):
                try:
                    os.remove(_p)
                except Exception:
                    pass
