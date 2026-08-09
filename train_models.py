"""
==============================================================
 Landslide Prediction System — Model Training Pipeline
==============================================================
Trains, evaluates and persists:
  1. Random Forest classifier
  2. XGBoost classifier
  3. DBSCAN spatial clustering (unsupervised risk zones)

Evaluation metrics: accuracy, precision, recall, F1, ROC-AUC
Model artifacts saved to  models/  directory.
"""

import numpy as np
import pandas as pd
import joblib
import json
from pathlib import Path

from sklearn.ensemble         import RandomForestClassifier
from sklearn.model_selection  import train_test_split, cross_val_score
from sklearn.preprocessing    import StandardScaler
from sklearn.impute           import SimpleImputer
from sklearn.metrics          import (
    accuracy_score, precision_score, recall_score,
    f1_score, classification_report, confusion_matrix, roc_auc_score
)
from sklearn.cluster          import DBSCAN
from sklearn.pipeline         import Pipeline
import xgboost as xgb
import warnings
warnings.filterwarnings("ignore")


# ─────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent
DATA_PATH   = BASE_DIR / "data"  / "landslide_dataset.csv"
MODEL_DIR   = BASE_DIR / "models"
MODEL_DIR.mkdir(exist_ok=True)

LABEL_MAP   = {0: "Low", 1: "Medium", 2: "High"}
FEATURES    = [
    "deformation_mm", "velocity_mm_yr", "coherence",
    "rainfall_mm", "slope_deg", "soil_moisture_pct",
    "elevation_m", "aspect_deg", "ndvi"
]


# ─────────────────────────────────────────────────────────────
# 1.  Load & prepare data
# ─────────────────────────────────────────────────────────────

def load_data(path: Path = DATA_PATH) -> tuple:
    """Load dataset, split features and labels."""
    if not path.exists():
        raise FileNotFoundError(
            f"Dataset not found at {path}. "
            "Run  python data/generate_dataset.py  first."
        )
    df = pd.read_csv(path)

    if "label" in df.columns:
        y_raw = df["label"]
    elif "risk_level" in df.columns:
        y_raw = df["risk_level"]
    else:
        raise ValueError("Dataset must contain either 'label' or 'risk_level' column")

    if y_raw.dtype == object:
        label_map = {"low": 0, "medium": 1, "high": 2}
        y = y_raw.astype(str).str.lower().map(label_map).fillna(0).astype(int).values
    else:
        y = pd.to_numeric(y_raw, errors="coerce").fillna(0).astype(int).values

    X = df[FEATURES].apply(pd.to_numeric, errors="coerce").values
    coords = df[["latitude", "longitude"]].values  # for DBSCAN
    print(f" Dataset loaded: {len(df)} rows | Features: {len(FEATURES)}")
    print(f"   Class distribution: {dict(pd.Series(y).value_counts().sort_index())}")
    return X, y, coords, df


# ─────────────────────────────────────────────────────────────
# 2.  Random Forest
# ─────────────────────────────────────────────────────────────

def train_random_forest(X_train, y_train) -> Pipeline:
    """Train a scaled Random Forest pipeline."""
    pipe = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
        ("clf", RandomForestClassifier(
            n_estimators    = 300,
            max_depth       = 12,
            min_samples_leaf= 5,
            class_weight    = "balanced",
            random_state    = 42,
            n_jobs          = -1
        ))
    ])
    pipe.fit(X_train, y_train)
    return pipe


# ─────────────────────────────────────────────────────────────
# 3.  XGBoost
# ─────────────────────────────────────────────────────────────

def train_xgboost(X_train, y_train) -> Pipeline:
    """Train a scaled XGBoost pipeline."""
    pipe = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
        ("clf", xgb.XGBClassifier(
            n_estimators      = 400,
            max_depth         = 6,
            learning_rate     = 0.05,
            subsample         = 0.8,
            colsample_bytree  = 0.8,
            use_label_encoder = False,
            eval_metric       = "mlogloss",
            random_state      = 42,
            n_jobs            = -1
        ))
    ])
    pipe.fit(X_train, y_train)
    return pipe


# ─────────────────────────────────────────────────────────────
# 4.  Evaluation helper
# ─────────────────────────────────────────────────────────────

def evaluate_model(model, X_test, y_test, name: str) -> dict:
    """Compute and print full evaluation metrics."""
    y_pred  = model.predict(X_test)
    y_proba = model.predict_proba(X_test)

    acc  = accuracy_score(y_test, y_pred)
    prec = precision_score(y_test, y_pred, average="weighted", zero_division=0)
    rec  = recall_score(y_test, y_pred, average="weighted", zero_division=0)
    f1   = f1_score(y_test, y_pred, average="weighted", zero_division=0)
    try:
        auc = roc_auc_score(y_test, y_proba, multi_class="ovr", average="weighted")
    except Exception:
        auc = float("nan")

    print(f"\n{'='*55}")
    print(f"  {name} — Evaluation Results")
    print(f"{'='*55}")
    print(f"  Accuracy  : {acc:.4f}")
    print(f"  Precision : {prec:.4f}")
    print(f"  Recall    : {rec:.4f}")
    print(f"  F1-Score  : {f1:.4f}")
    print(f"  ROC-AUC   : {auc:.4f}")
    print("\nClassification Report:")
    print(classification_report(
        y_test,
        y_pred,
        labels=[0, 1, 2],
        target_names=["Low", "Medium", "High"],
        zero_division=0,
    ))
    print("Confusion Matrix:")
    conf = confusion_matrix(y_test, y_pred, labels=[0, 1, 2])
    print(conf)

    return {
        "accuracy": acc,
        "precision": prec,
        "recall": rec,
        "f1": f1,
        "roc_auc": auc,
        "confusion_matrix": conf.tolist(),
    }


# ─────────────────────────────────────────────────────────────
# 5.  DBSCAN Spatial Clustering
# ─────────────────────────────────────────────────────────────

def run_dbscan(coords: np.ndarray, high_risk_mask: np.ndarray) -> np.ndarray:
    """
    Cluster high-risk pixel locations using DBSCAN to identify
    contiguous landslide-prone zones.
    
    Args:
        coords        : (N, 2) lat/lon array for ALL pixels
        high_risk_mask: Boolean mask — True for Medium/High risk pixels
    
    Returns:
        cluster_labels: Cluster ID per high-risk pixel (-1 = noise)
    """
    hr_coords = coords[high_risk_mask]
    if len(hr_coords) < 5:
        return np.full(high_risk_mask.sum(), -1)

    # eps in degrees (~0.01° ≈ 1 km at equator)
    db = DBSCAN(eps=0.05, min_samples=5, algorithm="ball_tree", metric="haversine")
    labels = db.fit_predict(np.radians(hr_coords))
    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    print(f"\nDBSCAN: {n_clusters} spatial clusters of high-risk pixels found.")
    return labels


# ─────────────────────────────────────────────────────────────
# 6.  Feature importance
# ─────────────────────────────────────────────────────────────

def get_feature_importance(model, model_name: str) -> pd.DataFrame:
    """Extract feature importance from tree-based model."""
    clf = model.named_steps["clf"]
    importance = clf.feature_importances_
    df = pd.DataFrame({
        "feature"   : FEATURES,
        "importance": importance
    }).sort_values("importance", ascending=False).reset_index(drop=True)
    print(f"\nFeature Importance — {model_name}:")
    print(df.to_string(index=False))
    return df


# ─────────────────────────────────────────────────────────────
# 7.  Main training orchestrator
# ─────────────────────────────────────────────────────────────

def main():
    # ── Load data ────────────────────────────────────────────
    X, y, coords, df = load_data()

    # ── Train / test split (80/20, stratified) ───────────────
    X_train, X_test, y_train, y_test, c_train, c_test = train_test_split(
        X, y, coords, test_size=0.20, stratify=y, random_state=42
    )
    print(f"\nTrain: {len(X_train)} | Test: {len(X_test)}")

    # ── Train models ─────────────────────────────────────────
    print("\n Training Random Forest...")
    rf_model = train_random_forest(X_train, y_train)

    print("⚡ Training XGBoost...")
    xgb_model = train_xgboost(X_train, y_train)

    # ── Evaluate ─────────────────────────────────────────────
    rf_metrics  = evaluate_model(rf_model,  X_test, y_test, "Random Forest")
    xgb_metrics = evaluate_model(xgb_model, X_test, y_test, "XGBoost")

    # ── Cross-validation (5-fold) ────────────────────────────
    print("\n5-Fold Cross-Validation (Random Forest):")
    cv_scores = cross_val_score(rf_model, X, y, cv=5, scoring="f1_weighted", n_jobs=-1)
    print(f"  F1 per fold: {cv_scores.round(4)}")
    print(f"  Mean ± Std : {cv_scores.mean():.4f} ± {cv_scores.std():.4f}")

    # ── Feature importance ────────────────────────────────────
    rf_importance  = get_feature_importance(rf_model,  "Random Forest")
    xgb_importance = get_feature_importance(xgb_model, "XGBoost")

    # ── DBSCAN clustering ─────────────────────────────────────
    y_pred_all   = np.asarray(rf_model.predict(X))
    high_risk_mask = y_pred_all >= 1   # Medium or High
    cluster_labels = run_dbscan(coords, high_risk_mask)

    # ── Save artifacts ────────────────────────────────────────
    joblib.dump(rf_model,  MODEL_DIR / "random_forest.pkl")
    joblib.dump(xgb_model, MODEL_DIR / "xgboost.pkl")
    joblib.dump(StandardScaler().fit(X), MODEL_DIR / "scaler.pkl")

    metrics_summary = {
        "random_forest" : rf_metrics,
        "xgboost"       : xgb_metrics,
        "features"      : FEATURES,
        "label_map"     : LABEL_MAP,
    }
    with open(MODEL_DIR / "metrics.json", "w") as f:
        json.dump(metrics_summary, f, indent=2)

    rf_importance.to_csv(MODEL_DIR  / "rf_feature_importance.csv",  index=False)
    xgb_importance.to_csv(MODEL_DIR / "xgb_feature_importance.csv", index=False)

    print(f"\n Models saved to  {MODEL_DIR}/")
    print("   random_forest.pkl | xgboost.pkl | metrics.json")

    return rf_model, xgb_model


if __name__ == "__main__":
    main()
