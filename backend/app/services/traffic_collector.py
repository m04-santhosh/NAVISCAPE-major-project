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


def train_lstm_from_db(db: Session, is_test: bool = False) -> Dict[str, Any]:
    """
    Retrieves real traffic observations from the database for junction 1,
    scales and formats the sequence data, trains the LSTM model, and saves
    the trained model and scaler to the ml/models directory.
    
    If is_test is True, trains on test data and saves to test artifacts.
    Otherwise, trains on real data and saves to production artifacts.
    """
    # Fetch all observations for junction 1 sorted by timestamp
    observations = (
        db.query(TrafficData)
        .filter(
            TrafficData.junction_id == 1,
            TrafficData.is_test == is_test,
            TrafficData.speed_ratio != None
        )
        .order_by(TrafficData.timestamp.asc())
        .all()
    )

    count = len(observations)
    # Threshold for training
    MIN_OBSERVATIONS = 120
    if count < MIN_OBSERVATIONS:
        return {
            "trained": False,
            "reason": f"Insufficient observations: {count}/{MIN_OBSERVATIONS} collected. More data is required.",
            "observation_count": count
        }

    # Extract speed ratios
    import numpy as np
    import joblib
    from sklearn.preprocessing import MinMaxScaler
    
    # Hide tensorflow log output for clean startup/logs
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.layers import LSTM, Dense, Dropout

    values = np.array([o.speed_ratio for o in observations], dtype="float32").reshape(-1, 1)

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
            "reason": f"Insufficient sequence length: sequence length is {len(X)}. Need more continuous data.",
            "observation_count": count
        }

    # Split train/test
    split = int(len(X) * 0.8)
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]

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
    model.fit(X_train, y_train, epochs=20, batch_size=32, validation_split=0.1, verbose=0)

    # 5. Save model and scaler (test vs prod)
    ml_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
        "ml", "models",
    )
    os.makedirs(ml_dir, exist_ok=True)
    
    suffix = "_test" if is_test else "_prod"
    model_path = os.path.join(ml_dir, f"traffic_lstm{suffix}.h5")
    scaler_path = os.path.join(ml_dir, f"traffic_scaler{suffix}.pkl")

    model.save(model_path)
    joblib.dump(scaler, scaler_path)

    # Reset lazy loader in traffic intelligence to reload models
    from . import traffic_intelligence
    traffic_intelligence._lstm_loaded = False
    traffic_intelligence._lstm_model = None
    traffic_intelligence._lstm_scaler = None

    return {
        "trained": True,
        "message": f"Successfully trained LSTM traffic prediction model on {count} observations.",
        "observation_count": count,
        "model_path": model_path,
        "scaler_path": scaler_path
    }


def predict_traffic_lstm(
    db: Session,
    junction_id: int,
    hours_ahead: int,
    use_test_model: bool = False
) -> Optional[List[dict]]:
    """
    Performs genuine LSTM traffic prediction for a junction if the model is available
    and 24 consecutive real observations exist in the database.
    """
    # 1. Load LSTM model and scaler
    global _lstm_model, _lstm_scaler
    suffix = "_test" if use_test_model else "_prod"
    
    ml_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
        "ml", "models",
    )
    model_path = os.path.join(ml_dir, f"traffic_lstm{suffix}.h5")
    scaler_path = os.path.join(ml_dir, f"traffic_scaler{suffix}.pkl")

    if not os.path.exists(model_path) or not os.path.exists(scaler_path):
        return None

    try:
        import joblib
        os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
        from tensorflow.keras.models import load_model  # type: ignore
        model = load_model(model_path, compile=False)
        scaler = joblib.load(scaler_path)
    except Exception:
        return None

    # 2. Fetch the recent real traffic observations for the last 24 hours
    # The required input sequence MUST come entirely from legitimate collected observations
    now = datetime.now()
    timestamps = [now - timedelta(hours=h) for h in range(24, 0, -1)]
    
    sequence = []
    for ts in timestamps:
        start_ts = ts - timedelta(minutes=30)
        end_ts = ts + timedelta(minutes=30)
        obs = (
            db.query(TrafficData)
            .filter(
                TrafficData.junction_id == junction_id,
                TrafficData.is_test == use_test_model,
                TrafficData.timestamp.between(start_ts, end_ts),
                TrafficData.speed_ratio != None
            )
            .order_by(TrafficData.timestamp.desc())
            .first()
        )
        if obs:
            sequence.append(float(obs.speed_ratio))
        else:
            # Missing observation in the window: cannot form complete input sequence
            logger.info(f"Missing observation for junction {junction_id} at {ts}. Cannot run LSTM prediction.")
            return None

    # Convert to numpy array and shape (1, 24, 1)
    import numpy as np
    seq_arr = np.array(sequence, dtype="float32").reshape(1, 24, 1)
    
    # Scale input
    scaled_seq = scaler.transform(seq_arr.reshape(-1, 1)).reshape(1, 24, 1)
    
    predictions = []
    current_window = scaled_seq.copy()
    
    for i in range(hours_ahead):
        # Predict speed ratio one step ahead
        pred_scaled = model.predict(current_window, verbose=0)
        pred_speed_ratio = float(scaler.inverse_transform(pred_scaled)[0][0])
        pred_speed_ratio = max(0.0, min(1.0, pred_speed_ratio))
        
        target_time = now + timedelta(hours=i)
        target_hour = target_time.hour
        
        # Estimate congestion level based on predicted speed ratio
        if pred_speed_ratio < 0.4:
            congestion = "critical"
        elif pred_speed_ratio < 0.7:
            congestion = "high"
        elif pred_speed_ratio < 0.9:
            congestion = "medium"
        else:
            congestion = "low"

        # Calculate a display-only vehicle count for the API contract
        predicted_count = int((1.0 - pred_speed_ratio) * MAX_VEHICLE_COUNT)

        predictions.append({
            "hour": target_hour,
            "timestamp": target_time.isoformat(),
            "predicted_vehicle_count": predicted_count,
            "congestion_level": congestion,
            "confidence": 0.90,
            "prediction_source": "lstm_model",
        })
        
        # Slide window: append predicted scaled value and drop first element
        next_val_scaled = pred_scaled[0][0]
        current_window = np.append(current_window[0][1:], [[next_val_scaled]], axis=0).reshape(1, 24, 1)
        
    return predictions
