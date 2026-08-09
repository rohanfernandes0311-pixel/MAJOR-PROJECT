"""Optional anomaly detection service.

The service uses Isolation Forest when available and degrades to a robust
z-score style heuristic if scikit-learn changes or a model cannot be fit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(slots=True)
class AnomalyDetectionService:
    contamination: float = 0.08
    random_state: int = 42

    def score(self, features: np.ndarray) -> dict[str, Any]:
        data = np.asarray(features, dtype=float)
        if data.ndim == 1:
            data = data.reshape(-1, 1)

        try:
            from sklearn.ensemble import IsolationForest

            model = IsolationForest(contamination=self.contamination, random_state=self.random_state)
            labels = model.fit_predict(data)
            scores = model.decision_function(data)
            return {
                "method": "isolation_forest",
                "anomaly_flags": labels.tolist(),
                "anomaly_scores": scores.tolist(),
            }
        except Exception:
            centered = data - np.nanmean(data, axis=0, keepdims=True)
            denom = np.nanstd(data, axis=0, keepdims=True) + 1e-9
            z = np.abs(centered / denom)
            score = np.nanmax(z, axis=1)
            flags = (score > 2.5).astype(int)
            return {
                "method": "robust_zscore",
                "anomaly_flags": flags.tolist(),
                "anomaly_scores": score.tolist(),
            }
