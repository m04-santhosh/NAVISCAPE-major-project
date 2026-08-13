"""
Traffic Collector & LSTM Service — NAVISCAPE Phase 8
Manages background traffic data collection, database persistence,
LSTM model training, and genuine LSTM prediction inference.
"""

import os
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from ..config import settings
from ..database import SessionLocal
from ..models.traffic import TrafficData
from .traffic_intelligence import MONITORED_JUNCTIONS, _fetch_tomtom_flow_point, MAX_VEHICLE_COUNT, HOUR_PATTERNS

logger = logging.getLogger(__name__)


async def fetch_and_store_junction_traffic(db: Session) -> int:
    """
    Fetches real TomTom traffic flow data for each monitored junction
    and stores the observation in the database.
    """
    api_key = settings.TOMTOM_API_KEY
    if not api_key:
        logger.warning("TomTom API key not configured. Cannot collect traffic observations.")
        return 0

    stored_count = 0
    now = datetime.now()

    for junc in MONITORED_JUNCTIONS:
        flow = await _fetch_tomtom_flow_point(junc["lat"], junc["lng"], api_key)
        if flow:
            # Check if an observation for this junction already exists at this exact minute
            exists = db.query(TrafficData).filter(
                TrafficData.junction_id == junc["id"],
                TrafficData.timestamp == now.replace(second=0, microsecond=0)
            ).first()

            if not exists:
                # We store actual TomTom speed metrics.
                # vehicle_count is set to 0 (non-nullable DB column placeholder).
                obs = TrafficData(
                    junction_id=junc["id"],
                    latitude=junc["lat"],
                    longitude=junc["lng"],
                    timestamp=now.replace(second=0, microsecond=0),
                    vehicle_count=0, 
                    avg_speed=flow["current_speed_kmh"],
                    free_flow_speed=flow["free_flow_speed_kmh"],
                    speed_ratio=flow["speed_ratio"],
                    congestion_level=None,  # Leave empty for real speed data or map logically
                    day_of_week=now.weekday(),
                    hour_of_day=now.hour,
                    is_test=False
                )
                db.add(obs)
                stored_count += 1

    if stored_count > 0:
        db.commit()
        logger.info(f"Stored {stored_count} real TomTom traffic observations at {now}")
    return stored_count


async def traffic_collector_loop():
    """Background loop that collects TomTom traffic data every 5 minutes."""
    logger.info("Starting periodic TomTom traffic collection background service...")
    while True:
        try:
            db = SessionLocal()
            try:
                await fetch_and_store_junction_traffic(db)
            finally:
                db.close()
        except Exception as e:
            logger.exception("Error in traffic collector background service loop:")
        
        # Run every 5 minutes (300 seconds)
        await asyncio.sleep(300)


def aggregate_5min_to_hourly(
    db: Session,
    junction_id: int = 1,
    is_test: bool = False
) -> List[Dict[str, Any]]:
    """
    Aggregates raw 5-minute TomTom observations into a clean hourly time series
    for the specified junction.
    
    Computes mean speed_ratio and mean avg_speed per 1-hour bucket.
    Returns a chronologically sorted list of dicts.
    """
    records = (
        db.query(TrafficData)
        .filter(
            TrafficData.junction_id == junction_id,
            TrafficData.is_test == is_test,
            TrafficData.speed_ratio != None
        )
        .order_by(TrafficData.timestamp.asc())
        .all()
    )

    if not records:
        return []

    hourly_buckets: Dict[datetime, List[TrafficData]] = {}
    for r in records:
        if not r.timestamp:
            continue
        hour_bucket = r.timestamp.replace(minute=0, second=0, microsecond=0)
        if hour_bucket not in hourly_buckets:
            hourly_buckets[hour_bucket] = []
        hourly_buckets[hour_bucket].append(r)

    series = []
    for dt_bucket in sorted(hourly_buckets.keys()):
        bucket_obs = hourly_buckets[dt_bucket]
        mean_ratio = sum(float(o.speed_ratio) for o in bucket_obs if o.speed_ratio is not None) / len(bucket_obs)
        valid_speeds = [float(o.avg_speed) for o in bucket_obs if o.avg_speed is not None]
        mean_speed = sum(valid_speeds) / len(valid_speeds) if valid_speeds else None

        series.append({
            "timestamp": dt_bucket,
            "speed_ratio": round(mean_ratio, 4),
            "avg_speed": round(mean_speed, 1) if mean_speed is not None else None,
            "hour_of_day": dt_bucket.hour,
            "day_of_week": dt_bucket.weekday(),
            "sample_count": len(bucket_obs)
        })

    return series


def train_lstm_from_db(
    db: Session,
    junction_id: int = 1,
    is_test: bool = False
) -> Dict[str, Any]:
    """
    Retrieves real aggregated hourly traffic observations from database for junction_id,
    scales and formats sequence data, trains the LSTM model, and saves
    trained model, scaler, and training metadata to ml/models.
    
    If is_test is True, trains on test data and saves to test artifacts.
    Otherwise, trains on real data and saves to production artifacts.
    """
    hourly_series = aggregate_5min_to_hourly(db, junction_id=junction_id, is_test=is_test)
    count = len(hourly_series)

    MIN_HOURLY_OBSERVATIONS = 120
    if count < MIN_HOURLY_OBSERVATIONS:
        return {
            "trained": False,
            "status": "insufficient_real_data",
            "reason": f"Insufficient real hourly traffic observations for LSTM training: {count}/{MIN_HOURLY_OBSERVATIONS} aggregated hours available.",
            "junction_id": junction_id,
            "hourly_observation_count": count,
            "required_hourly_observations": MIN_HOURLY_OBSERVATIONS,
        }

    import numpy as np
    import joblib
    import json
    from sklearn.preprocessing import MinMaxScaler
    
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.layers import LSTM, Dense, Dropout

    values = np.array([h["speed_ratio"] for h in hourly_series], dtype="float32").reshape(-1, 1)

    # 1. Scale data
    scaler = MinMaxScaler(feature_range=(0, 1))
    scaled = scaler.fit_transform(values)

    # 2. Create sequences (WINDOW_SIZE = 24)
    WINDOW_SIZE = 24
    X, y = [], []
    for i in range(len(scaled) - WINDOW_SIZE):
        X.append(scaled[i : i + WINDOW_SIZE])
        y.append(scaled[i + WINDOW_SIZE])
    
    X = np.array(X)
    y = np.array(y)

    if len(X) < 10:
        return {
            "trained": False,
            "status": "insufficient_sequence_length",
            "reason": f"Insufficient sequence length: sequence length is {len(X)}. Need more continuous hourly data.",
            "junction_id": junction_id,
            "hourly_observation_count": count,
        }

    # Split train/validation
    split = int(len(X) * 0.8)
    X_train, X_val = X[:split], X[split:]
    y_train, y_val = y[:split], y[split:]

    # 3. Build model
    model = Sequential([
        LSTM(64, return_sequences=True, input_shape=(WINDOW_SIZE, 1)),
        Dropout(0.2),
        LSTM(32, return_sequences=False),
        Dropout(0.2),
        Dense(16, activation='relu'),
        Dense(1),
    ])
    model.compile(optimizer='adam', loss='mse', metrics=['mae'])

    # 4. Fit model (20 epochs)
    history = model.fit(X_train, y_train, epochs=20, batch_size=32, validation_data=(X_val, y_val), verbose=0)

    val_loss = float(history.history['val_loss'][-1]) if 'val_loss' in history.history else None
    val_mae = float(history.history['val_mae'][-1]) if 'val_mae' in history.history else None

    # 5. Save model, scaler, and metadata (test vs prod artifacts)
    ml_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
        "ml", "models",
    )
    os.makedirs(ml_dir, exist_ok=True)
    
    suffix = "_test" if is_test else "_prod"
    if junction_id == 1:
        model_path = os.path.join(ml_dir, f"traffic_lstm{suffix}.h5")
        scaler_path = os.path.join(ml_dir, f"traffic_scaler{suffix}.pkl")
        meta_path = os.path.join(ml_dir, f"traffic_lstm_meta{suffix}.json")
    else:
        model_path = os.path.join(ml_dir, f"traffic_lstm{suffix}_j{junction_id}.h5")
        scaler_path = os.path.join(ml_dir, f"traffic_scaler{suffix}_j{junction_id}.pkl")
        meta_path = os.path.join(ml_dir, f"traffic_lstm_meta{suffix}_j{junction_id}.json")

    model.save(model_path)
    joblib.dump(scaler, scaler_path)

    raw_count = (
        db.query(TrafficData)
        .filter(
            TrafficData.junction_id == junction_id,
            TrafficData.is_test == is_test,
        )
        .count()
    )

    metadata = {
        "model_version": "1.0.0",
        "trained_at": datetime.now().isoformat(),
        "is_test": is_test,
        "junction_id": junction_id,
        "raw_observation_count": raw_count,
        "hourly_observation_count": count,
        "sequence_length": WINDOW_SIZE,
        "feature_columns": ["speed_ratio"],
        "scaling_method": "MinMaxScaler(0, 1)",
        "train_split_ratio": 0.8,
        "validation_loss_mse": val_loss,
        "validation_mae": val_mae,
    }
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2)

    # Reset lazy loader in traffic intelligence to reload models
    from . import traffic_intelligence
    traffic_intelligence._lstm_loaded = False
    traffic_intelligence._lstm_model = None
    traffic_intelligence._lstm_scaler = None

    return {
        "trained": True,
        "status": "success",
        "message": f"Successfully trained LSTM traffic prediction model for junction {junction_id} on {count} real hourly observations.",
        "junction_id": junction_id,
        "hourly_observation_count": count,
        "model_path": model_path,
        "scaler_path": scaler_path,
        "metadata": metadata,
    }


def predict_traffic_lstm(
    db: Session,
    junction_id: int = 1,
    hours_ahead: int = 24,
    use_test_model: bool = False
) -> Optional[List[dict]]:
    """
    Performs genuine LSTM traffic prediction for a junction if the model is available
    and 24 consecutive real hourly observations exist in the database.
    """
    # 1. Load LSTM model and scaler
    ml_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
        "ml", "models",
    )
    suffix = "_test" if use_test_model else "_prod"
    if junction_id == 1:
        model_path = os.path.join(ml_dir, f"traffic_lstm{suffix}.h5")
        scaler_path = os.path.join(ml_dir, f"traffic_scaler{suffix}.pkl")
    else:
        model_path = os.path.join(ml_dir, f"traffic_lstm{suffix}_j{junction_id}.h5")
        scaler_path = os.path.join(ml_dir, f"traffic_scaler{suffix}_j{junction_id}.pkl")

    if not os.path.exists(model_path) or not os.path.exists(scaler_path):
        return None

    try:
        import joblib
        os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
        from tensorflow.keras.models import load_model  # type: ignore
        model = load_model(model_path, compile=False)
        scaler = joblib.load(scaler_path)
    except Exception as e:
        logger.warning(f"Failed to load LSTM model for junction {junction_id}: {e}")
        return None

    # 2. Fetch real hourly aggregated observations for the junction
    hourly_series = aggregate_5min_to_hourly(db, junction_id=junction_id, is_test=use_test_model)

    if len(hourly_series) < 24:
        logger.info(f"Insufficient hourly observations ({len(hourly_series)}/24) for junction {junction_id}. Cannot run LSTM prediction.")
        return None

    # Take the latest 24 consecutive hourly speed_ratios
    recent_24 = [float(h["speed_ratio"]) for h in hourly_series[-24:]]

    import numpy as np
    seq_arr = np.array(recent_24, dtype="float32").reshape(1, 24, 1)
    
    # Scale input using exact same scaler fit during training
    scaled_seq = scaler.transform(seq_arr.reshape(-1, 1)).reshape(1, 24, 1)
    
    now = datetime.now()
    predictions = []
    current_window = scaled_seq.copy()
    
    for i in range(hours_ahead):
        pred_scaled = model.predict(current_window, verbose=0)
        pred_speed_ratio = float(scaler.inverse_transform(pred_scaled)[0][0])
        pred_speed_ratio = max(0.0, min(1.0, pred_speed_ratio))
        
        target_time = now + timedelta(hours=i)
        target_hour = target_time.hour
        
        if pred_speed_ratio < 0.4:
            congestion = "critical"
        elif pred_speed_ratio < 0.7:
            congestion = "high"
        elif pred_speed_ratio < 0.9:
            congestion = "medium"
        else:
            congestion = "low"

        predicted_count = int((1.0 - pred_speed_ratio) * MAX_VEHICLE_COUNT)

        predictions.append({
            "hour": target_hour,
            "timestamp": target_time.isoformat(),
            "predicted_vehicle_count": predicted_count,
            "predicted_speed_ratio": round(pred_speed_ratio, 4),
            "congestion_level": congestion,
            "confidence": 0.90,
            "prediction_source": "lstm_model",
        })
        
        next_val_scaled = pred_scaled[0][0]
        current_window = np.append(current_window[0][1:], [[next_val_scaled]], axis=0).reshape(1, 24, 1)
        
    return predictions


def get_lstm_model_status(
    db: Session,
    junction_id: int = 1,
    use_test_model: bool = False
) -> Dict[str, Any]:
    """
    Returns the current training, observation count, and availability status of the LSTM model.
    Does not expose raw filesystem paths or credentials.
    """
    ml_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
        "ml", "models",
    )
    suffix = "_test" if use_test_model else "_prod"
    if junction_id == 1:
        model_path = os.path.join(ml_dir, f"traffic_lstm{suffix}.h5")
        scaler_path = os.path.join(ml_dir, f"traffic_scaler{suffix}.pkl")
        meta_path = os.path.join(ml_dir, f"traffic_lstm_meta{suffix}.json")
    else:
        model_path = os.path.join(ml_dir, f"traffic_lstm{suffix}_j{junction_id}.h5")
        scaler_path = os.path.join(ml_dir, f"traffic_scaler{suffix}_j{junction_id}.pkl")
        meta_path = os.path.join(ml_dir, f"traffic_lstm_meta{suffix}_j{junction_id}.json")

    model_exists = os.path.exists(model_path) and os.path.exists(scaler_path)

    raw_count = (
        db.query(TrafficData)
        .filter(
            TrafficData.junction_id == junction_id,
            TrafficData.is_test == use_test_model,
        )
        .count()
    )

    hourly_series = aggregate_5min_to_hourly(db, junction_id=junction_id, is_test=use_test_model)
    hourly_count = len(hourly_series)

    metadata = None
    if os.path.exists(meta_path):
        try:
            import json
            with open(meta_path, "r") as f:
                metadata = json.load(f)
        except Exception:
            pass

    if model_exists:
        status = "trained_and_available"
    elif hourly_count < 120:
        status = "insufficient_real_data"
    else:
        status = "not_trained"

    return {
        "status": status,
        "junction_id": junction_id,
        "is_test": use_test_model,
        "raw_observation_count": raw_count,
        "hourly_observation_count": hourly_count,
        "required_hourly_observations": 120,
        "model_trained": model_exists,
        "metadata": metadata,
    }
