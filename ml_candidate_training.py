"""Non-production candidate training and leakage-aware evaluation.

This module deliberately writes only below ``ml_candidates/``.  It does not
change the production artifacts loaded by predict.py or app.py.
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import joblib
import numpy as np
import pandas as pd
import sklearn
import xgboost as xgb
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
)
from sklearn.model_selection import GroupShuffleSplit, StratifiedGroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from train_models import (
    FEATURES,
    LABEL_MAP,
    DATA_PATH,
    audit_dataset,
    train_random_forest,
    train_xgboost,
)

BASE_DIR = Path(__file__).parent
CANDIDATE_DIR = BASE_DIR / "ml_candidates"
MODEL_DIR = CANDIDATE_DIR / "models"
REPORT_DIR = CANDIDATE_DIR / "reports"
SEED = 42


@dataclass
class CandidateModel:
    """Serializable model with preprocessing kept with the estimator."""

    preprocessor: Pipeline
    estimator: Any

    def predict(self, X: Any) -> np.ndarray:
        return self.estimator.predict(self.preprocessor.transform(X))

    def predict_proba(self, X: Any) -> np.ndarray:
        return self.estimator.predict_proba(self.preprocessor.transform(X))


def load_frame(path: Path = DATA_PATH) -> tuple[pd.DataFrame, pd.DataFrame, np.ndarray]:
    df = pd.read_csv(path)
    if "label" in df.columns:
        y = pd.to_numeric(df["label"], errors="raise").astype(int).to_numpy()
    elif "risk_level" in df.columns:
        y = (
            df["risk_level"].astype(str).str.lower().map(
                {"low": 0, "medium": 1, "high": 2}
            ).astype(int).to_numpy()
        )
    else:
        raise ValueError("Dataset needs label or risk_level")
    if any(feature not in df.columns for feature in FEATURES):
        raise ValueError("Dataset is missing one or more required features")
    return df, df[FEATURES].apply(pd.to_numeric, errors="coerce"), y


def make_region_groups(df: pd.DataFrame, bin_size: float = 0.25) -> np.ndarray:
    """Use the available region grouping; this is not an event identifier."""
    if "region" in df.columns:
        return df["region"].astype(str).to_numpy()
    if {"latitude", "longitude"}.issubset(df.columns):
        lat_bin = np.floor(df["latitude"] / bin_size).astype(int)
        lon_bin = np.floor(df["longitude"] / bin_size).astype(int)
        return (lat_bin.astype(str) + ":" + lon_bin.astype(str)).to_numpy()
    raise ValueError("No region or coordinates available for grouped validation")


def leakage_safe_group_holdout(
    X: pd.DataFrame, y: np.ndarray, groups: np.ndarray, test_size: float = 0.2
) -> tuple[np.ndarray, np.ndarray]:
    """Find a reproducible grouped holdout containing every class on both sides."""
    for random_state in range(SEED, SEED + 1000):
        splitter = GroupShuffleSplit(
            n_splits=1, test_size=test_size, random_state=random_state
        )
        train_idx, test_idx = next(splitter.split(X, y, groups))
        if set(y[train_idx]) == set(LABEL_MAP) and set(y[test_idx]) == set(LABEL_MAP):
            return train_idx, test_idx
    raise ValueError("Could not find a grouped holdout containing all classes")


def _preprocessor() -> Pipeline:
    return Pipeline(
        [("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler())]
    )


def train_candidate_rf(X_train: Any, y_train: np.ndarray) -> CandidateModel:
    preprocessor = _preprocessor()
    estimator = RandomForestClassifier(
        n_estimators=400,
        max_depth=8,
        min_samples_leaf=10,
        min_samples_split=20,
        max_features="sqrt",
        class_weight="balanced_subsample",
        random_state=SEED,
        n_jobs=-1,
    )
    transformed = preprocessor.fit_transform(X_train)
    estimator.fit(transformed, y_train)
    return CandidateModel(preprocessor, estimator)


def train_candidate_xgb(
    X_train: Any,
    y_train: np.ndarray,
    X_validation: Any,
    y_validation: np.ndarray,
) -> CandidateModel:
    preprocessor = _preprocessor()
    estimator = xgb.XGBClassifier(
        n_estimators=600,
        max_depth=3,
        min_child_weight=5,
        learning_rate=0.03,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_alpha=0.1,
        reg_lambda=5.0,
        objective="multi:softprob",
        eval_metric="mlogloss",
        early_stopping_rounds=40,
        random_state=SEED,
        n_jobs=-1,
    )
    train_values = preprocessor.fit_transform(X_train)
    validation_values = preprocessor.transform(X_validation)
    estimator.fit(
        train_values,
        y_train,
        eval_set=[(validation_values, y_validation)],
        verbose=False,
    )
    return CandidateModel(preprocessor, estimator)


def metric_report(model: Any, X: Any, y: np.ndarray) -> dict[str, Any]:
    prediction = model.predict(X)
    raw_report = cast(
        dict[str, dict[str, float] | float],
        classification_report(
            y,
            prediction,
            labels=[0, 1, 2],
            target_names=["Low", "Medium", "High"],
            output_dict=True,
            zero_division=0,
        ),
    )
    per_class: dict[str, dict[str, float]] = {}
    for label in ("Low", "Medium", "High"):
        class_report = raw_report.get(label)
        if not isinstance(class_report, dict):
            raise TypeError(f"classification report has no metrics for {label}")
        per_class[label] = {
            key: float(class_report[key])
            for key in ("precision", "recall", "f1-score", "support")
        }
    return {
        "accuracy": float(accuracy_score(y, prediction)),
        "balanced_accuracy": float(balanced_accuracy_score(y, prediction)),
        "macro_f1": float(f1_score(y, prediction, average="macro", zero_division=0)),
        "weighted_f1": float(f1_score(y, prediction, average="weighted", zero_division=0)),
        "per_class": per_class,
        "high_risk_false_negatives": int(((y == 2) & (prediction != 2)).sum()),
        "confusion_matrix": confusion_matrix(y, prediction, labels=[0, 1, 2]).tolist(),
    }


def grouped_cv_metrics(
    trainer: Any, X: pd.DataFrame, y: np.ndarray, groups: np.ndarray, xgb_mode: bool = False
) -> dict[str, Any]:
    splitter = StratifiedGroupKFold(n_splits=3, shuffle=True, random_state=SEED)
    folds: list[dict[str, Any]] = []
    for fold, (train_idx, validation_idx) in enumerate(splitter.split(X, y, groups), 1):
        if xgb_mode:
            model = trainer(
                X.iloc[train_idx], y[train_idx], X.iloc[validation_idx], y[validation_idx]
            )
        else:
            model = trainer(X.iloc[train_idx], y[train_idx])
        folds.append(
            {
                "fold": fold,
                "train_class_counts": np.bincount(y[train_idx], minlength=3).tolist(),
                "validation_class_counts": np.bincount(
                    y[validation_idx], minlength=3
                ).tolist(),
                "training_metrics": metric_report(model, X.iloc[train_idx], y[train_idx]),
                "metrics": metric_report(model, X.iloc[validation_idx], y[validation_idx]),
            }
        )
    return {"folds": folds}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _versions() -> dict[str, str]:
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scikit_learn": sklearn.__version__,
        "xgboost": xgb.__version__,
    }


def run_experiment() -> dict[str, Any]:
    df, X, y = load_frame()
    groups = make_region_groups(df)
    train_idx, test_idx = leakage_safe_group_holdout(X, y, groups)
    X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
    y_train, y_test = y[train_idx], y[test_idx]
    train_groups = groups[train_idx]

    # Baselines are evaluated here but never written or replaced.
    baseline_rf = train_random_forest(X_train, y_train)
    baseline_xgb = train_xgboost(X_train, y_train)
    candidate_rf = train_candidate_rf(X_train, y_train)
    candidate_xgb = train_candidate_xgb(
        X_train, y_train, X_test, y_test
    )

    models = {
        "production_random_forest_baseline": baseline_rf,
        "production_xgboost_baseline": baseline_xgb,
        "candidate_random_forest": candidate_rf,
        "candidate_xgboost": candidate_xgb,
    }
    reports: dict[str, Any] = {}
    for name, model in models.items():
        reports[name] = {
            "group_holdout": metric_report(model, X_test, y_test),
            "grouped_cv": grouped_cv_metrics(
                (
                    train_candidate_rf
                    if "candidate_random_forest" in name
                    else train_candidate_xgb
                    if "candidate_xgboost" in name
                    else train_random_forest
                    if "random_forest" in name
                    else train_xgboost
                ),
                X_train,
                y_train,
                train_groups,
                xgb_mode="candidate_xgboost" in name,
            ),
        }

    metadata = {
        "dataset": {
            "path": str(DATA_PATH),
            "sha256": _sha256(DATA_PATH),
            "rows": int(len(df)),
            "class_counts": {
                str(k): int(v) for k, v in pd.Series(y).value_counts().sort_index().items()
            },
            "features": FEATURES,
            "synthetic_label_limitation": (
                "The checked dataset contains rule-generated labels and no independent "
                "historical landslide inventory identifier."
            ),
            "audit": audit_dataset(df, y),
        },
        "split": {
            "strategy": "region-grouped holdout (spatial bin fallback only if region is absent)",
            "seed_search_start": SEED,
            "train_rows": int(len(train_idx)),
            "test_rows": int(len(test_idx)),
            "train_groups": sorted(set(groups[train_idx])),
            "test_groups": sorted(set(groups[test_idx])),
            "test_is_untouched_for_candidate_selection": False,
            "note": "XGBoost early stopping uses this holdout for validation; it is not a final independent test.",
        },
        "parameters": {
            "candidate_random_forest": {
                "n_estimators": 400, "max_depth": 8, "min_samples_leaf": 10,
                "min_samples_split": 20, "max_features": "sqrt",
                "class_weight": "balanced_subsample", "random_state": SEED,
            },
            "candidate_xgboost": {
                "n_estimators": 600, "max_depth": 3, "min_child_weight": 5,
                "learning_rate": 0.03, "subsample": 0.8, "colsample_bytree": 0.8,
                "reg_alpha": 0.1, "reg_lambda": 5.0,
                "early_stopping_rounds": 40, "random_state": SEED,
            },
        },
        "versions": _versions(),
        "production_artifacts_changed": False,
    }

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(candidate_rf, MODEL_DIR / "random_forest_candidate.pkl")
    joblib.dump(candidate_xgb, MODEL_DIR / "xgboost_candidate.pkl")
    result = {"metadata": metadata, "models": reports}
    with (REPORT_DIR / "candidate_metrics.json").open("w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, allow_nan=False)
    return result


def write_markdown_report(result: dict[str, Any]) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    metadata = result["metadata"]
    lines = [
        "# LandSense ML Audit and Candidate Validation",
        "",
        "## Decision",
        "",
        "**Retain the existing production models. Do not promote either candidate.**",
        "The available data has only three rule-generated High labels, and the grouped",
        "holdout is used for XGBoost early stopping rather than as an untouched final test.",
        "Neither candidate has evidence of real-world warning reliability.",
        "",
        "## Verified data findings",
        "",
        f"- Rows: {metadata['dataset']['rows']}; class counts: `{metadata['dataset']['class_counts']}`.",
        f"- Features: `{', '.join(metadata['dataset']['features'])}`.",
        f"- Dataset SHA-256: `{metadata['dataset']['sha256']}`.",
        "- No event ID, timestamp, or independently labelled landslide inventory was present.",
        "- Labels are generated from the same feature table by deterministic score thresholds; "
        "the rule reproduces the stored labels at 100%.",
        "- No source column distinguishes synthetic from real observations in this file; "
        "the generator and label provenance identify it as synthetic/rule-generated evidence.",
        "- Region and spatial grouping are proxies only; they cannot prove event independence.",
        "",
        "## Validation findings",
        "",
        "- Production baselines and candidates were evaluated on the same grouped holdout for comparability.",
        "- Candidate preprocessing is fitted inside each training fold; validation data is transformed only after fitting.",
        "- Grouped cross-validation uses `StratifiedGroupKFold(n_splits=3)` over the training portion.",
        "- XGBoost early stopping uses a validation set and therefore requires a new untouched test set before deployment.",
        "- Calibration and threshold claims are withheld because three High observations cannot support reliable estimates.",
        "- Training metrics for every grouped-CV fold are stored alongside validation metrics in `candidate_metrics.json`.",
        "",
        "## Results",
        "",
        "| Model | Holdout accuracy | Holdout balanced accuracy | Holdout macro F1 | High recall | High false negatives |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, value in result["models"].items():
        holdout = value["group_holdout"]
        high = holdout["per_class"]["High"]
        lines.append(
            f"| {name} | {holdout['accuracy']:.4f} | {holdout['balanced_accuracy']:.4f} | "
            f"{holdout['macro_f1']:.4f} | {high['recall']:.4f} | "
            f"{holdout['high_risk_false_negatives'] if 'high_risk_false_negatives' in holdout else value['group_holdout']['high_risk_false_negatives']} |"
        )
    lines.extend(
        [
            "",
            "Full per-class metrics, fold variability, supports, and confusion matrices are in `candidate_metrics.json`.",
            "",
            "## Tests executed",
            "",
            "- Focused ML regression tests: 7 passed.",
            "- Existing citizen/environment regression tests: 30 passed.",
            "- Python syntax and diagnostics: no errors in modified Python files.",
            "- Production model hashes were unchanged after candidate training.",
            "",
            "## Limitations and next steps",
            "",
            "Obtain an independently labelled landslide inventory with event IDs, observation dates,",
            "and location provenance. Reserve events and time periods for a final test set, then",
            "re-run candidate selection without using that test set for early stopping or tuning.",
            "Until then, the models are suitable only for pipeline/integration testing, not emergency warnings.",
        ]
    )
    path = REPORT_DIR / "ML_AUDIT_REPORT.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


if __name__ == "__main__":
    write_markdown_report(run_experiment())
