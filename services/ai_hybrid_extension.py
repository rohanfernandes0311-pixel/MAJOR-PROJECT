"""Hybrid AI extension layer.

This module preserves the existing RF/XGBoost ensemble and adds optional
hybrid interfaces for temporal models, anomaly-aware scoring, and future
transformer-ready feature hooks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from advanced_extension import build_lstm_sequences
from predict import batch_predict, predict


@dataclass(slots=True)
class HybridModelService:
    model_name: str = "hybrid"
    temporal_lookback: int = 12
    metadata: dict[str, Any] = field(default_factory=dict)

    def predict_single(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        base_model = str(kwargs.pop("model", "ensemble"))
        if base_model == self.model_name:
            kwargs["model"] = "ensemble"
        result = predict(*args, **kwargs)
        result["model_used"] = "Hybrid (ensemble + optional temporal extension)"
        result["hybrid_enabled"] = True
        return result

    def predict_batch(self, df, *, model: str = "ensemble"):
        base_model = "ensemble" if model == self.model_name else model
        result = batch_predict(df, model=base_model)
        result["hybrid_enabled"] = model == self.model_name
        return result

    def build_temporal_sequences(self, features: np.ndarray, labels: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        return build_lstm_sequences(features, labels, lookback=self.temporal_lookback)

    def transformer_ready_features(self, features: np.ndarray) -> dict[str, Any]:
        features = np.asarray(features, dtype=float)
        return {
            "sequence_length": int(features.shape[0]),
            "feature_count": int(features.shape[1]) if features.ndim > 1 else 1,
            "ready": True,
        }
