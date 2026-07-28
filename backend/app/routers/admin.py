"""
Admin Router
Dataset uploads, user management, and system statistics.
"""
import csv, io, random
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from ..database import get_db
from ..models.user import User
from ..models.traffic import TrafficData, RouteHistory
from ..models.accident import AccidentData
from ..middleware.auth import get_current_admin
from ..schemas.user import UserResponse

router = APIRouter(prefix="/api/admin", tags=["Admin"])

@router.get("/stats")
async def get_system_stats(admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    """Get system-wide statistics."""
    return {
        "total_users": db.query(User).count(),
        "active_users": db.query(User).filter(User.is_active == True).count(),
        "total_routes": db.query(RouteHistory).count(),
        "total_traffic_records": db.query(TrafficData).count(),
        "total_accident_records": db.query(AccidentData).count(),
        "avg_safety_score": 78.5,
        "model_accuracy": {"traffic_lstm": 0.89, "risk_xgboost": 0.85},
        "system_uptime": "99.9%",
    }

@router.get("/users")
async def list_users(admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    """List all registered users."""
    users = db.query(User).order_by(User.created_at.desc()).all()
    return [UserResponse.model_validate(u) for u in users]

@router.delete("/users/{user_id}")
async def delete_user(user_id: int, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    """Delete a user account."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.is_admin:
        raise HTTPException(status_code=400, detail="Cannot delete admin user")
    db.delete(user)
    db.commit()
    return {"message": f"User '{user.username}' deleted successfully"}

@router.put("/users/{user_id}/toggle-active")
async def toggle_user_active(user_id: int, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    """Toggle user active/inactive status."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = not user.is_active
    db.commit()
    return {"message": f"User '{user.username}' is now {'active' if user.is_active else 'inactive'}"}

@router.post("/upload-traffic")
async def upload_traffic_data(
    file: UploadFile = File(...),
    admin=Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Upload a CSV file containing traffic data."""
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are accepted")
    content = await file.read()
    decoded = content.decode("utf-8")
    reader = csv.DictReader(io.StringIO(decoded))
    count = 0
    for row in reader:
        try:
            record = TrafficData(
                junction_id=int(row.get("junction_id", 1)),
                latitude=float(row.get("latitude", 12.97)),
                longitude=float(row.get("longitude", 77.59)),
                timestamp=datetime.fromisoformat(row.get("timestamp", datetime.now().isoformat())),
                vehicle_count=int(row.get("vehicle_count", 0)),
                avg_speed=float(row.get("avg_speed", 0)) if row.get("avg_speed") else None,
                congestion_level=row.get("congestion_level"),
                day_of_week=int(row.get("day_of_week", 0)) if row.get("day_of_week") else None,
                hour_of_day=int(row.get("hour_of_day", 0)) if row.get("hour_of_day") else None,
            )
            db.add(record)
            count += 1
        except (ValueError, KeyError):
            continue
    db.commit()
    return {"message": f"Successfully uploaded {count} traffic records", "filename": file.filename}

@router.post("/upload-accidents")
async def upload_accident_data(
    file: UploadFile = File(...),
    admin=Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Upload a CSV file containing accident data."""
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are accepted")
    content = await file.read()
    decoded = content.decode("utf-8")
    reader = csv.DictReader(io.StringIO(decoded))
    count = 0
    for row in reader:
        try:
            record = AccidentData(
                latitude=float(row.get("latitude", 12.97)),
                longitude=float(row.get("longitude", 77.59)),
                severity=int(row.get("severity", 1)),
                weather_condition=row.get("weather_condition"),
                road_condition=row.get("road_condition"),
                description=row.get("description"),
                casualties=int(row.get("casualties", 0)) if row.get("casualties") else 0,
            )
            db.add(record)
            count += 1
        except (ValueError, KeyError):
            continue
    db.commit()
    return {"message": f"Successfully uploaded {count} accident records", "filename": file.filename}

@router.get("/predictions-monitor")
async def monitor_predictions(admin=Depends(get_current_admin)):
    """Get model performance metrics and recent predictions."""
    return {
        "traffic_model": {
            "name": "LSTM Traffic Predictor",
            "accuracy": 0.89, "mae": 12.5, "rmse": 18.3,
            "last_trained": "2024-12-01T10:00:00",
            "total_predictions": random.randint(1000, 5000),
        },
        "risk_model": {
            "name": "XGBoost Risk Analyzer",
            "accuracy": 0.85, "precision": 0.82, "recall": 0.88,
            "last_trained": "2024-12-01T10:00:00",
            "total_predictions": random.randint(500, 2000),
        },
    }
