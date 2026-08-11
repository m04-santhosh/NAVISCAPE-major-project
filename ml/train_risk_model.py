"""
NAVISCAPE - Legitimate XGBoost Risk Prediction Model Training
Trains an XGBoost classifier on 95,000+ real historical accident records from Karnataka.
"""
import os
import sqlite3
import pandas as pd
import numpy as np
import joblib
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import classification_report, accuracy_score
from xgboost import XGBClassifier

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "backend", "naviscape.db")
MODEL_DIR = os.path.join(BASE_DIR, "ml", "models")
BACKEND_MODEL_DIR = os.path.join(BASE_DIR, "backend", "app", "ml_models")
os.makedirs(MODEL_DIR, exist_ok=True)
os.makedirs(BACKEND_MODEL_DIR, exist_ok=True)

SEVERITY_MAP = {
    "Damage Only": 0,
    "Simple Injury": 1,
    "Grievous Injury": 2,
    "Fatal": 3,
}

def load_and_preprocess():
    print("[1/4] Loading real accident dataset from SQLite database...")
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"Database file not found at {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    query = """
        SELECT latitude, longitude, severity, weather, road_condition, surface_condition
        FROM accident_data
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL AND severity IS NOT NULL
    """
    df = pd.read_sql(query, conn)
    conn.close()

    print(f"   Loaded {len(df)} total accident records from DB.")

    # Filter to known severities
    df = df[df['severity'].isin(SEVERITY_MAP.keys())].copy()
    df['target'] = df['severity'].map(SEVERITY_MAP)

    # Clean text features
    df['weather'] = df['weather'].fillna('Clear').astype(str).str.strip()
    df['road_condition'] = df['road_condition'].fillna('Not Applicable').astype(str).str.strip()
    df['surface_condition'] = df['surface_condition'].fillna('Not Applicable').astype(str).str.strip()

    print(f"   Valid training records: {len(df)}")
    return df

def train_xgboost_model(df):
    print("\n[2/4] Encoding categorical features...")
    le_weather = LabelEncoder()
    le_road = LabelEncoder()
    le_surface = LabelEncoder()

    df['weather_enc'] = le_weather.fit_transform(df['weather'])
    df['road_enc'] = le_road.fit_transform(df['road_condition'])
    df['surface_enc'] = le_surface.fit_transform(df['surface_condition'])

    features = ['latitude', 'longitude', 'weather_enc', 'road_enc', 'surface_enc']
    X = df[features].values
    y = df['target'].values

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    print(f"   Training samples: {len(X_train)}, Testing samples: {len(X_test)}")

    print("\n[3/4] Fitting XGBoost Classifier on real accident data...")
    model = XGBClassifier(
        n_estimators=150,
        max_depth=6,
        learning_rate=0.08,
        random_state=42,
        eval_metric='mlogloss',
    )
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    print(f"\n   Model Accuracy on Test Set: {acc:.4f} ({acc:.2%})")
    print(classification_report(y_test, y_pred, target_names=list(SEVERITY_MAP.keys()), zero_division=0))

    print("\n[4/4] Saving model artifacts...")
    model_payload = {
        "model": model,
        "weather_encoder": le_weather,
        "road_encoder": le_road,
        "surface_encoder": le_surface,
        "features": features,
        "severity_map": SEVERITY_MAP,
        "risk_weights": {0: 25.0, 1: 50.0, 2: 75.0, 3: 95.0},
    }

    model_path = os.path.join(MODEL_DIR, "risk_xgboost.pkl")
    joblib.dump(model_payload, model_path)
    print(f"   Saved to ML dir: {model_path}")

    backend_model_path = os.path.join(BACKEND_MODEL_DIR, "risk_xgboost.pkl")
    joblib.dump(model_payload, backend_model_path)
    print(f"   Saved to Backend dir: {backend_model_path}")

    return acc

if __name__ == "__main__":
    print("=" * 60)
    print("NAVISCAPE - Real XGBoost Risk Prediction Model Training")
    print("=" * 60)
    df = load_and_preprocess()
    acc = train_xgboost_model(df)
    print(f"\nTraining completed successfully! Model Accuracy: {acc:.2%}")

