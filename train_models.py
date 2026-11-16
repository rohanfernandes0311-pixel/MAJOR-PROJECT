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

import argparse
import numpy as np
import pandas as pd
import joblib
import json
from pathlib import Path

from sklearn.ensemble         import RandomForestClassifier
from sklearn.model_selection import (
    train_test_split, cross_val_score, StratifiedKFold, cross_validate
)
from sklearn.preprocessing    import StandardScaler
from sklearn.impute           import SimpleImputer
from sklearn.metrics          import (
    accuracy_score, precision_score, recall_score,
    f1_score, classification_report, confusion_matrix, roc_auc_score,
    balanced_accuracy_score
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
    balanced_acc = balanced_accuracy_score(y_test, y_pred)
    prec = precision_score(y_test, y_pred, average="weighted", zero_division=0)
    rec  = recall_score(y_test, y_pred, average="weighted", zero_division=0)
    f1   = f1_score(y_test, y_pred, average="weighted", zero_division=0)
    macro_f1 = f1_score(y_test, y_pred, average="macro", zero_division=0)
    per_class = classification_report(
        y_test, y_pred, labels=[0, 1, 2],
        target_names=["Low", "Medium", "High"],
        output_dict=True, zero_division=0,
    )
    try:
        auc = roc_auc_score(y_test, y_proba, multi_class="ovr", average="weighted")
    except Exception:
        auc = float("nan")

    print(f"\n{'='*55}")
    print(f"  {name} — Evaluation Results")
    print(f"{'='*55}")
    print(f"  Accuracy  : {acc:.4f}")
    print(f"  Balanced accuracy: {balanced_acc:.4f}")
    print(f"  Precision : {prec:.4f}")
    print(f"  Recall    : {rec:.4f}")
    print(f"  F1-Score  : {f1:.4f}")
    print(f"  Macro F1  : {macro_f1:.4f}")
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
        "balanced_accuracy": balanced_acc,
        "precision": prec,
        "recall": rec,
        "f1": f1,
        "macro_f1": macro_f1,
        "per_class": {
            label: {
                key: per_class[label][key]
                for key in ("precision", "recall", "f1-score", "support")
            }
            for label in ("Low", "Medium", "High")
        },
        "high_risk_false_negatives": int(((y_test == 2) & (y_pred != 2)).sum()),
        "roc_auc": auc,
        "confusion_matrix": conf.tolist(),
    }


def _recomputed_generator_labels(df: pd.DataFrame) -> np.ndarray:
    """Recreate the fallback generator's rule to audit label provenance."""
    values = df[FEATURES].astype(float)
    score = (
        0.28 * values["deformation_mm"] / max(values["deformation_mm"].max(), 1e-9)
        + 0.18 * values["velocity_mm_yr"] / max(values["velocity_mm_yr"].max(), 1e-9)
        + 0.18 * values["rainfall_mm"] / max(values["rainfall_mm"].max(), 1e-9)
        + 0.14 * values["slope_deg"] / max(values["slope_deg"].max(), 1e-9)
        + 0.12 * values["soil_moisture_pct"]
        / max(values["soil_moisture_pct"].max(), 1e-9)
        - 0.10 * values["coherence"]
    )
    return pd.cut(
        score, bins=[-np.inf, 0.33, 0.60, np.inf], labels=[0, 1, 2]
    ).astype(int).to_numpy()


def audit_dataset(df: pd.DataFrame, y: np.ndarray) -> dict:
    """Report provenance and structural risks without changing artifacts."""
    feature_frame = df[FEATURES]
    recomputed = _recomputed_generator_labels(df)
    class_counts = pd.Series(y).value_counts().sort_index()
    return {
        "rows": int(len(df)),
        "feature_count": len(FEATURES),
        "missing_feature_values": int(feature_frame.isna().sum().sum()),
        "duplicate_feature_rows": int(feature_frame.duplicated().sum()),
        "duplicate_full_rows": int(df.duplicated().sum()),
        "class_counts": {str(k): int(v) for k, v in class_counts.items()},
        "label_rule_reproduction_rate": float(np.mean(recomputed == y)),
        "label_provenance": (
            "Labels reproduce the feature-derived rule in generate_dataset.py; "
            "this is synthetic/rule-generated evidence, not independent ground truth."
        ),
        "high_risk_rows": int((y == 2).sum()),
    }


def cross_validate_model(model, X, y) -> dict:
    """Evaluate generalization with folds that can represent every class."""
    min_class_count = int(pd.Series(y).value_counts().min())
    n_splits = min(5, min_class_count)
    if n_splits < 2:
        raise ValueError("At least two rows per class are required for cross-validation")
    cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
    scores = cross_validate(
        model, X, y, cv=cv,
        scoring={
            "accuracy": "accuracy",
            "balanced_accuracy": "balanced_accuracy",
            "macro_f1": "f1_macro",
            "weighted_f1": "f1_weighted",
        },
        return_train_score=True,
        n_jobs=-1,
    )
    metrics = ("accuracy", "balanced_accuracy", "macro_f1", "weighted_f1")
    return {
        "folds": n_splits,
        "test": {
            metric: {
                "mean": float(np.mean(scores[f"test_{metric}"])),
                "std": float(np.std(scores[f"test_{metric}"])),
                "values": [float(v) for v in scores[f"test_{metric}"]],
            }
            for metric in metrics
        },
        "train": {
            metric: float(np.mean(scores[f"train_{metric}"]))
            for metric in metrics
        },
    }


def audit_only(output_path: Path | None = None) -> dict:
    """Run diagnostics without replacing production model artifacts."""
    X, y, _coords, df = load_data()
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, stratify=y, random_state=42
    )
    report = {
        "audit": audit_dataset(df, y),
        "evaluation_protocol": {
            "holdout": "stratified 80/20 split, random_state=42",
            "cross_validation": "stratified folds capped by the rarest class",
            "production_artifacts_changed": False,
        },
        "models": {},
    }
    for name, trainer in (
        ("random_forest", train_random_forest),
        ("xgboost", train_xgboost),
    ):
        model = trainer(X_train, y_train)
        report["models"][name] = {
            "holdout": evaluate_model(model, X_test, y_test, name),
            "cross_validation": cross_validate_model(model, X, y),
        }
    if output_path is None:
        output_path = MODEL_DIR / "audit_metrics.json"
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, allow_nan=False)
    print(f"\nAudit report saved to {output_path}; production artifacts were not replaced.")
    return report


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
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--audit-only",
        action="store_true",
        help="evaluate models without replacing production artifacts",
    )
    parser.add_argument("--audit-output", type=Path, default=None)
    args = parser.parse_args()
    if args.audit_only:
        audit_only(args.audit_output)
    else:
        main()
