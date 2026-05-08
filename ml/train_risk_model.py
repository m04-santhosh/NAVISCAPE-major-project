"""
NAVISCAPE - XGBoost Risk Prediction Model Training
Trains an XGBoost classifier to predict accident severity and a Random Forest
model to predict accident probability at a given location.
"""
import os, numpy as np, pandas as pd, joblib
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import classification_report, accuracy_score
from sklearn.ensemble import RandomForestClassifier

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
MODEL_DIR = os.path.join(os.path.dirname(__file__), "models")
os.makedirs(MODEL_DIR, exist_ok=True)

def load_and_preprocess():
    print("[1/6] Loading accident data...")
    df = pd.read_csv(os.path.join(DATA_DIR, "accident_data.csv"))
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df['hour'] = df['timestamp'].dt.hour
    df['day_of_week'] = df['timestamp'].dt.dayofweek
    df['month'] = df['timestamp'].dt.month
    df['is_night'] = df['hour'].apply(lambda h: 1 if h < 6 or h >= 22 else 0)
    df['is_rush_hour'] = df['hour'].apply(lambda h: 1 if h in [8,9,17,18,19] else 0)
    print(f"   Loaded {len(df)} accident records")
    return df

def train_severity_model(df):
    print("\n[2/6] Training XGBoost Severity Classifier...")
    le_weather = LabelEncoder()
    le_road = LabelEncoder()
    df['weather_enc'] = le_weather.fit_transform(df['weather_condition'].fillna('unknown'))
    df['road_enc'] = le_road.fit_transform(df['road_condition'].fillna('unknown'))
    features = ['latitude','longitude','hour','day_of_week','month',
                'is_night','is_rush_hour','weather_enc','road_enc']
    X = df[features].values
    y = df['severity'].values
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    print(f"   Train: {len(X_train)}, Test: {len(X_test)}")

    print("[3/6] Fitting XGBoost model...")
    from xgboost import XGBClassifier
    model = XGBClassifier(n_estimators=100, max_depth=6, learning_rate=0.1,
                          random_state=42, use_label_encoder=False,
                          eval_metric='mlogloss')
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    print(f"   Accuracy: {acc:.4f}")
    print(classification_report(y_test, y_pred, zero_division=0))

    # Save
    model_path = os.path.join(MODEL_DIR, "risk_xgboost.pkl")
    joblib.dump({"model": model, "weather_encoder": le_weather,
                 "road_encoder": le_road, "features": features}, model_path)
    print(f"   Saved: {model_path}")
    return acc

def train_probability_model(df):
    print("[4/6] Training Random Forest Probability Model...")
    le_weather = LabelEncoder()
    le_road = LabelEncoder()
    df['weather_enc'] = le_weather.fit_transform(df['weather_condition'].fillna('unknown'))
    df['road_enc'] = le_road.fit_transform(df['road_condition'].fillna('unknown'))
    # Binary: high risk (severity >= 3) vs low risk
    df['high_risk'] = (df['severity'] >= 3).astype(int)
    features = ['latitude','longitude','hour','day_of_week','is_night',
                'is_rush_hour','weather_enc','road_enc']
    X = df[features].values
    y = df['high_risk'].values
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    print("[5/6] Fitting Random Forest...")
    model = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42)
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    print(f"   Accuracy: {acc:.4f}")
    print(classification_report(y_test, y_pred, zero_division=0))

    model_path = os.path.join(MODEL_DIR, "risk_rf.pkl")
    joblib.dump({"model": model, "features": features}, model_path)
    print(f"   Saved: {model_path}")

    print("[6/6] Feature Importance:")
    importances = model.feature_importances_
    for f, imp in sorted(zip(features, importances), key=lambda x: -x[1]):
        print(f"   {f}: {imp:.4f}")
    return acc

if __name__ == "__main__":
    print("="*50)
    print("NAVISCAPE - Risk Prediction Model Training")
    print("="*50)
    df = load_and_preprocess()
    acc1 = train_severity_model(df)
    acc2 = train_probability_model(df)
    print(f"\nResults: XGBoost={acc1:.2%}, RandomForest={acc2:.2%}")
    print("Training complete!")
