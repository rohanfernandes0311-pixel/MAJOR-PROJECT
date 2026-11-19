"""
==============================================================
 Landslide Prediction Engine
==============================================================
Loads trained models and classifies new sensor readings.
Integrates with the alert system.
"""

import numpy as np
import joblib
import pandas as pd
from pathlib import Path

BASE_DIR  = Path(__file__).parent
MODEL_DIR = BASE_DIR / "models"
FEATURES  = [
    "deformation_mm", "velocity_mm_yr", "coherence",
    "rainfall_mm", "slope_deg", "soil_moisture_pct",
    "elevation_m", "aspect_deg", "ndvi"
]
LABEL_MAP = {0: "Low", 1: "Medium", 2: "High"}


def _validated_features(values: list[float]) -> np.ndarray:
    """Reject malformed sensor input before it reaches a persisted model."""
    try:
        array = np.asarray(values, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("All prediction features must be numeric") from exc
    if array.shape != (len(FEATURES),) or not np.isfinite(array).all():
        raise ValueError(
            f"Prediction requires {len(FEATURES)} finite numeric features"
        )
    return array


def load_models():
    """Load trained RF and XGB models from disk."""
    rf_path  = MODEL_DIR / "random_forest.pkl"
    xgb_path = MODEL_DIR / "xgboost.pkl"

    if not rf_path.exists() or not xgb_path.exists():
        raise FileNotFoundError(
            "Trained models not found. Run: python train_models.py"
        )
    rf_model  = joblib.load(rf_path)
    xgb_model = joblib.load(xgb_path)
    return rf_model, xgb_model


def predict(
    deformation_mm   : float,
    velocity_mm_yr   : float,
    coherence        : float,
    rainfall_mm      : float,
    slope_deg        : float,
    soil_moisture_pct: float,
    elevation_m      : float = 800.0,
    aspect_deg       : float = 180.0,
    ndvi             : float = 0.4,
    model            : str   = "xgboost",   # "random_forest" | "xgboost" | "ensemble"
) -> dict:
    """
    Predict landslide risk for a single pixel / location.
    
    Returns:
        {
          "risk_label"   : "Low" | "Medium" | "High",
          "risk_code"    : 0 | 1 | 2,
          "confidence"   : float,          # probability of predicted class
          "probabilities": [p_low, p_med, p_high],
          "model_used"   : str,
          "feature_values": dict
        }
    """
    rf_model, xgb_model = load_models()

    feature_values = _validated_features([
        deformation_mm, velocity_mm_yr, coherence,
        rainfall_mm, slope_deg, soil_moisture_pct,
        elevation_m, aspect_deg, ndvi
    ])
    X = feature_values.reshape(1, -1)

    if model == "random_forest":
        proba    = rf_model.predict_proba(X)[0]
        pred_cls = int(np.argmax(proba))
        used     = "Random Forest"
    elif model == "xgboost":
        proba    = xgb_model.predict_proba(X)[0]
        pred_cls = int(np.argmax(proba))
        used     = "XGBoost"
    elif model == "ensemble":
        proba_rf  = rf_model.predict_proba(X)[0]
        proba_xgb = xgb_model.predict_proba(X)[0]
        proba     = (proba_rf + proba_xgb) / 2.0
        pred_cls  = int(np.argmax(proba))
        used      = "Ensemble (RF + XGB)"
    else:
        raise ValueError(f"Unknown model: {model}")

    return {
        "risk_label"    : LABEL_MAP[pred_cls],
        "risk_code"     : pred_cls,
        "confidence"    : float(proba[pred_cls]),
        "probabilities" : {
            "Low"   : float(proba[0]),
            "Medium": float(proba[1]),
            "High"  : float(proba[2]),
        },
        "model_used"    : used,
        "feature_values": dict(zip(FEATURES, X[0].tolist())),
    }


def explain_prediction(feature_values: dict[str, float], model: str = "ensemble") -> dict:
    """Return exact single-reference Shapley contributions for model scores.

    The reference row is each fitted pipeline's imputer median vector. Values
    describe model-score differences from that reference, not causal effects.
    """
    if model not in {"random_forest", "xgboost", "ensemble"}:
        raise ValueError(f"Unknown model: {model}")
    if not isinstance(feature_values, dict) or set(feature_values) != set(FEATURES):
        raise ValueError(f"feature_values must contain exactly: {', '.join(FEATURES)}")
    row = _validated_features([feature_values[name] for name in FEATURES])
    rf_model, xgb_model = load_models()
    models = {
        "random_forest": [("Random Forest", rf_model)],
        "xgboost": [("XGBoost", xgb_model)],
        "ensemble": [("Random Forest", rf_model), ("XGBoost", xgb_model)],
    }[model]
    n = len(FEATURES)
    masks = np.arange(1 << n, dtype=np.uint16)
    output = {}
    contributions_by_model = []
    base_by_model = []
    current_by_model = []

    for model_name, pipeline in models:
        medians = np.asarray(pipeline.named_steps["imputer"].statistics_, dtype=float)
        coalitions = np.tile(medians, (1 << n, 1))
        for feature_index in range(n):
            included = ((masks >> feature_index) & 1).astype(bool)
            coalitions[included, feature_index] = row[feature_index]
        values = np.asarray(pipeline.predict_proba(coalitions), dtype=float)
        base_by_model.append(values[0])
        current_by_model.append(values[-1])
        contribution = np.zeros((n, values.shape[1]), dtype=float)
        factorial = [1]
        for k in range(1, n + 1):
            factorial.append(factorial[-1] * k)
        denominator = float(factorial[n])
        for feature_index in range(n):
            bit = 1 << feature_index
            for mask in range(1 << n):
                if mask & bit:
                    continue
                size = int(mask.bit_count())
                weight = factorial[size] * factorial[n - size - 1] / denominator
                contribution[feature_index] += weight * (values[mask | bit] - values[mask])
        contributions_by_model.append(contribution)
        output[model_name] = contribution

    mean = lambda arrays: np.mean(np.stack(arrays), axis=0)
    base = mean(base_by_model)
    current = mean(current_by_model)
    contributions = mean(contributions_by_model)
    return {
        "method": "Exact Shapley values over all 2^9 feature coalitions",
        "reference": "Each selected model's fitted imputer median vector",
        "model_used": {"random_forest": "Random Forest", "xgboost": "XGBoost", "ensemble": "Ensemble (RF + XGB)"}[model],
        "feature_order": FEATURES,
        "base_probabilities": {LABEL_MAP[i]: float(base[i]) for i in range(len(base))},
        "prediction_probabilities": {LABEL_MAP[i]: float(current[i]) for i in range(len(current))},
        "contributions": {
            FEATURES[i]: {LABEL_MAP[j]: float(contributions[i, j]) for j in range(contributions.shape[1])}
            for i in range(n)
        },
        "model_contributions": {
            name: {
                FEATURES[i]: {LABEL_MAP[j]: float(values[i, j]) for j in range(values.shape[1])}
                for i in range(n)
            }
            for name, values in output.items()
        },
        "limitations": [
            "Contributions describe model-score changes from the reference row; they are not causal effects.",
            "Prediction scores are not calibrated real-world probabilities.",
            "The reference row is a fitted preprocessing baseline, not a representative local population.",
        ],
    }


def batch_predict(df: pd.DataFrame, model: str = "ensemble") -> pd.DataFrame:
    """Predict risk for a DataFrame with the feature columns."""
    rf_model, xgb_model = load_models()

    missing = [f for f in FEATURES if f not in df.columns]
    if missing:
        raise ValueError(f"DataFrame missing columns: {missing}")

    try:
        X = df[FEATURES].to_numpy(dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("All prediction features must be numeric") from exc
    if not np.isfinite(X).all():
        raise ValueError("All prediction features must be finite")

    if model == "ensemble":
        proba = (rf_model.predict_proba(X) + xgb_model.predict_proba(X)) / 2
    elif model == "random_forest":
        proba = rf_model.predict_proba(X)
    else:
        proba = xgb_model.predict_proba(X)

    pred_cls = np.argmax(proba, axis=1)
    result   = df.copy()
    result["risk_code"]      = pred_cls
    result["risk_label"]     = [LABEL_MAP[c] for c in pred_cls]
    result["confidence"]     = proba[np.arange(len(proba)), pred_cls]
    result["prob_low"]       = proba[:, 0]
    result["prob_medium"]    = proba[:, 1]
    result["prob_high"]      = proba[:, 2]
    return result


if __name__ == "__main__":
    # Quick test
    result = predict(
        deformation_mm    = 28.5,
        velocity_mm_yr    = 65.0,
        coherence         = 0.45,
        rainfall_mm       = 160.0,
        slope_deg         = 35.0,
        soil_moisture_pct = 82.0,
        model             = "ensemble"
    )
    print("Prediction result:")
    for k, v in result.items():
        print(f"  {k}: {v}")
