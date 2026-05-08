"""
NAVISCAPE - LSTM Traffic Prediction Model Training
Trains an LSTM neural network on historical traffic data to predict future vehicle counts.
"""
import os, numpy as np, pandas as pd, joblib
from sklearn.preprocessing import MinMaxScaler
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
MODEL_DIR = os.path.join(os.path.dirname(__file__), "models")
os.makedirs(MODEL_DIR, exist_ok=True)

WINDOW_SIZE = 24  # Use 24 hours of history to predict next hour

def load_and_preprocess():
    print("[1/5] Loading traffic data...")
    df = pd.read_csv(os.path.join(DATA_DIR, "traffic_data.csv"))
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values(['junction_id', 'timestamp'])
    print(f"   Loaded {len(df)} records for {df['junction_id'].nunique()} junctions")
    return df

def create_sequences(data, window_size):
    X, y = [], []
    for i in range(len(data) - window_size):
        X.append(data[i:i+window_size])
        y.append(data[i+window_size])
    return np.array(X), np.array(y)

def build_model(input_shape):
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.layers import LSTM, Dense, Dropout
    model = Sequential([
        LSTM(64, return_sequences=True, input_shape=input_shape),
        Dropout(0.2),
        LSTM(32, return_sequences=False),
        Dropout(0.2),
        Dense(16, activation='relu'),
        Dense(1),
    ])
    model.compile(optimizer='adam', loss='mse', metrics=['mae'])
    return model

def train():
    df = load_and_preprocess()
    # Use junction 1 (Silk Board) as primary training data
    junction_df = df[df['junction_id'] == 1].copy()
    values = junction_df['vehicle_count'].values.reshape(-1, 1).astype('float32')

    print("[2/5] Scaling data...")
    scaler = MinMaxScaler(feature_range=(0, 1))
    scaled = scaler.fit_transform(values)

    print("[3/5] Creating sequences (window={})...".format(WINDOW_SIZE))
    X, y = create_sequences(scaled, WINDOW_SIZE)
    split = int(len(X) * 0.8)
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]
    print(f"   Train: {len(X_train)}, Test: {len(X_test)}")

    print("[4/5] Building and training LSTM model...")
    model = build_model((WINDOW_SIZE, 1))
    model.summary()
    history = model.fit(X_train, y_train, epochs=20, batch_size=32,
                        validation_split=0.1, verbose=1)

    print("[5/5] Evaluating model...")
    loss, mae = model.evaluate(X_test, y_test, verbose=0)
    print(f"   Test Loss (MSE): {loss:.4f}")
    print(f"   Test MAE: {mae:.4f}")

    # Save
    model_path = os.path.join(MODEL_DIR, "traffic_lstm.h5")
    scaler_path = os.path.join(MODEL_DIR, "traffic_scaler.pkl")
    model.save(model_path)
    joblib.dump(scaler, scaler_path)
    print(f"\n   Model saved: {model_path}")
    print(f"   Scaler saved: {scaler_path}")

    # Sample predictions
    print("\n[SAMPLE PREDICTIONS]")
    preds = model.predict(X_test[:5], verbose=0)
    preds_actual = scaler.inverse_transform(preds)
    actual = scaler.inverse_transform(y_test[:5].reshape(-1,1))
    for i in range(5):
        print(f"   Predicted: {preds_actual[i][0]:.0f}, Actual: {actual[i][0]:.0f}")

if __name__ == "__main__":
    print("="*50)
    print("NAVISCAPE - LSTM Traffic Model Training")
    print("="*50)
    train()
    print("\nTraining complete!")
