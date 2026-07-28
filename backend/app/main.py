"""
NAVISCAPE - FastAPI Application Entry Point
Intelligent Navigation System for Predictive Traffic Analysis and Risk-Aware Routing.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import init_db, SessionLocal
from .models.user import User
from .middleware.auth import hash_password
from .routers import auth, navigation, traffic, prediction, admin


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    # Startup: initialize database and create default admin
    try:
        init_db()
        _create_default_admin()
        print("Database initialized.")
    except Exception as e:
        import traceback
        print("Database initialization skipped:", e)
        traceback.print_exc()
    print(f"\n{'='*60}")
    print(f"  NAVISCAPE v{settings.APP_VERSION} - Server Started")
    print(f"  API Docs: http://localhost:8000/docs")
    print(f"  Database: {settings.DATABASE_URL}")
    print(f"{'='*60}\n")
    yield
    # Shutdown
    print("\nNAVISCAPE Server shutting down...")


def _create_default_admin():
    """Create a default admin user if none exists."""
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.is_admin == True).first()
        if not existing:
            admin_user = User(
                username="admin",
                email="admin@naviscape.ai",
                hashed_password=hash_password("admin123"),
                full_name="System Administrator",
                is_admin=True,
                is_active=True,
            )
            db.add(admin_user)
            db.commit()
            print("[INIT] Default admin created: admin / admin123")
    finally:
        db.close()


# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    description="Intelligent Navigation System for Predictive Traffic Analysis and Risk-Aware Routing",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth.router)
app.include_router(navigation.router)
app.include_router(traffic.router)
app.include_router(prediction.router)
app.include_router(admin.router)


@app.get("/", tags=["Root"])
async def root():
    """Health check endpoint."""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "docs": "/docs",
    }


@app.get("/api/health", tags=["Root"])
async def health_check():
    """API health check."""
    return {"status": "healthy", "version": settings.APP_VERSION}
