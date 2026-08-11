"""
XGBoost Risk Prediction Service
Loads the trained XGBoost severity classification model and executes inference
on real historical accident patterns.
"""

import os
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

_model_payload: Optional[Dict[str, Any]] = None
_model_loaded: bool = False


def _load_xgboost_model() -> Optional[Dict[str, Any]]:
    """Lazy load the trained XGBoost model payload from disk."""
    global _model_payload, _model_loaded
    if _model_loaded:
        return _model_payload

    _model_loaded = True
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    possible_paths = [
        os.path.join(base_dir, "app", "ml_models", "risk_xgboost.pkl"),
        os.path.join(os.path.dirname(base_dir), "ml", "models", "risk_xgboost.pkl"),
    ]

    for path in possible_paths:
        if os.path.exists(path):
            try:
                import joblib
                _model_payload = joblib.load(path)
                logger.info(f"Successfully loaded XGBoost risk model from {path}")
                return _model_payload
            except Exception as e:
                logger.error(f"Failed to load XGBoost model from {path}: {e}")

    logger.warning("XGBoost risk model artifact not found on disk.")
    return None


def predict_xgboost_risk(
    latitude: float,
    longitude: float,
    weather: str = "Clear",
    road_condition: str = "Not Applicable",
    surface_condition: str = "Not Applicable",
) -> Dict[str, Any]:
    """
    Executes genuine XGBoost inference for accident risk at given coordinates.
    Returns predicted severity class, probability distribution, and scaled ML risk score.
    """
    payload = _load_xgboost_model()
    if not payload:
        return {
            "model_loaded": False,
            "model_name": "xgboost_unavailable",
            "predicted_severity": None,
            "predicted_risk_score": None,
            "probabilities": {},
        }

    try:
        import numpy as np

        model = payload["model"]
        weather_enc = payload["weather_encoder"]
        road_enc = payload["road_encoder"]
        surface_enc = payload["surface_encoder"]
        SEVERITY_MAP = payload["severity_map"]
        INV_SEVERITY_MAP = {v: k for k, v in SEVERITY_MAP.items()}
        RISK_WEIGHTS = payload["risk_weights"]

        # Safe transform helper
        def safe_transform(encoder, val, fallback):
            val_clean = str(val).strip() if val else fallback
            if val_clean in encoder.classes_:
                return encoder.transform([val_clean])[0]
            if fallback in encoder.classes_:
                return encoder.transform([fallback])[0]
            return 0

        w_val = safe_transform(weather_enc, weather, "Clear")
        r_val = safe_transform(road_enc, road_condition, "Not Applicable")
        s_val = safe_transform(surface_enc, surface_condition, "Not Applicable")

        feature_vector = np.array([[latitude, longitude, w_val, r_val, s_val]])

        # Inference
        probs = model.predict_proba(feature_vector)[0]
        pred_class_idx = int(model.predict(feature_vector)[0])
        pred_severity = INV_SEVERITY_MAP.get(pred_class_idx, "Unknown")

        # Weighted ML risk score based on severity probability distribution
        ml_risk_score = sum(probs[idx] * RISK_WEIGHTS.get(idx, 50.0) for idx in range(len(probs)))

        probs_dict = {
            INV_SEVERITY_MAP.get(idx, f"class_{idx}"): round(float(prob), 4)
            for idx, prob in enumerate(probs)
        }

        return {
            "model_loaded": True,
            "model_name": "xgboost_severity_classifier",
            "predicted_severity": pred_severity,
            "predicted_risk_score": round(float(ml_risk_score), 1),
            "probabilities": probs_dict,
        }

    except Exception as e:
        logger.error(f"Error during XGBoost risk inference: {e}")
        return {
            "model_loaded": False,
            "model_name": "xgboost_error",
            "predicted_severity": None,
            "predicted_risk_score": None,
            "probabilities": {},
            "error": str(e),
        }
