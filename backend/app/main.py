"""
NAVISCAPE - FastAPI Application Entry Point
Intelligent Navigation System for Predictive Traffic Analysis and Risk-Aware Routing.
"""

import os
import logging
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from .config import settings
from .database import init_db, get_db
from .routers import auth, navigation, traffic, prediction, accidents, road_hazard, police_station, hospital, women_safety

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    try:
        init_db()
        print("Database initialized.")
    except Exception as e:
        import traceback
        print("Database initialization warning:", e)
        traceback.print_exc()
    print(f"\n{'='*60}")
    print(f"  NAVISCAPE v{settings.APP_VERSION} - Server Started")
    print(f"  API Docs: http://localhost:8000/docs")
    print(f"  Database: {settings.DATABASE_URL}")
    print(f"{'='*60}\n")

    # Start periodic traffic data collection
    from .services.traffic_collector import traffic_collector_loop
    collector_task = asyncio.create_task(traffic_collector_loop())

    yield

    # Cancel periodic traffic data collection
    collector_task.cancel()
    try:
        await collector_task
    except asyncio.CancelledError:
        pass
    print("\nNAVISCAPE Server shutting down...")


# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    description="Intelligent Navigation System for Predictive Traffic Analysis and Risk-Aware Routing",
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global unhandled exception handler to prevent stack traces and configuration leak
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Mask unhandled exceptions to prevent information disclosure in production."""
    logger.exception(f"Unhandled exception in request {request.method} {request.url.path}: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An internal server error occurred. Please contact system support.",
            "status": "error"
        }
    )

# Register routers
app.include_router(auth.router)
app.include_router(navigation.router)
app.include_router(traffic.router)
app.include_router(prediction.router)
app.include_router(accidents.router)
app.include_router(road_hazard.router)
app.include_router(police_station.router)
app.include_router(hospital.router)
app.include_router(women_safety.router)


@app.get("/", tags=["Root"])
async def root():
    """Root health check endpoint."""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "docs": "/docs" if settings.DEBUG else None,
    }


@app.get("/api/health", tags=["Root"])
async def health_check(db: Session = Depends(get_db)):
    """API health check verifying database and major model/external dependencies."""
    health_status = {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "database": "unknown",
        "services": {
            "tomtom_configured": False,
            "xgboost_risk_model": "unloaded",
            "lstm_traffic_model": "unloaded"
        }
    }

    # 1. Database Check
    try:
        db.execute(text("SELECT 1"))
        health_status["database"] = "connected"
    except Exception:
        health_status["status"] = "unhealthy"
        health_status["database"] = "connection_failed"

    # 2. TomTom Config Check
    if settings.TOMTOM_API_KEY:
        health_status["services"]["tomtom_configured"] = True

    # 3. XGBoost Model Check
    from .services.risk_ml import _load_xgboost_model
    try:
        xgb_payload = _load_xgboost_model()
        if xgb_payload:
            health_status["services"]["xgboost_risk_model"] = "loaded"
        else:
            health_status["services"]["xgboost_risk_model"] = "unavailable"
    except Exception:
        health_status["services"]["xgboost_risk_model"] = "error"

    # 4. LSTM Model Check
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    prod_model_path = os.path.join(base_dir, "ml", "models", "traffic_lstm_prod.h5")
    if os.path.exists(prod_model_path):
        health_status["services"]["lstm_traffic_model"] = "trained"
    else:
        health_status["services"]["lstm_traffic_model"] = "untrained (requires more real data)"

    if health_status["status"] == "unhealthy":
        raise HTTPException(status_code=500, detail=health_status)

    return health_status
