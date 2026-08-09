"""streamlit run "files (2)/app.py"
Phase 2 advanced extension helpers.

This module keeps advanced ideas decoupled from the mandatory Phase 1 pipeline.
It includes:
  - Temporal sequence builder for deformation/rainfall/coherence
  - Optional LSTM trainer (runs only if TensorFlow is installed)
"""

from __future__ import annotations

import importlib
from typing import Tuple

import numpy as np


def build_lstm_sequences(
    features: np.ndarray,
    labels: np.ndarray,
    lookback: int = 12,
) -> Tuple[np.ndarray, np.ndarray]:
    """Convert tabular time-ordered data into LSTM sequences."""
    if lookback < 2:
        raise ValueError("lookback must be >= 2")
    if len(features) != len(labels):
        raise ValueError("features and labels must have the same length")
    if len(features) <= lookback:
        raise ValueError("not enough rows for the requested lookback window")

    x_seq = []
    y_seq = []
    for i in range(lookback, len(features)):
        x_seq.append(features[i - lookback:i])
        y_seq.append(labels[i])

    return np.asarray(x_seq, dtype=float), np.asarray(y_seq, dtype=int)


def train_lstm_optional(
    x_train: np.ndarray,
    y_train: np.ndarray,
    x_val: np.ndarray,
    y_val: np.ndarray,
    epochs: int = 20,
    batch_size: int = 32,
):
    """Train an LSTM classifier if TensorFlow is installed; else raise guidance."""
    try:
        keras_mod = importlib.import_module("tensorflow.keras")
        layers_mod = importlib.import_module("tensorflow.keras.layers")
    except Exception as exc:
        raise RuntimeError(
            "TensorFlow is not installed. Install it with: pip install tensorflow"
        ) from exc

    Sequential = getattr(keras_mod, "Sequential")
    LSTM = getattr(layers_mod, "LSTM")
    Dense = getattr(layers_mod, "Dense")
    Dropout = getattr(layers_mod, "Dropout")

    n_steps = x_train.shape[1]
    n_features = x_train.shape[2]
    n_classes = int(np.max(y_train)) + 1

    model = Sequential(
        [
            LSTM(64, input_shape=(n_steps, n_features), return_sequences=True),
            Dropout(0.2),
            LSTM(32),
            Dropout(0.2),
            Dense(32, activation="relu"),
            Dense(n_classes, activation="softmax"),
        ]
    )

    model.compile(
        optimizer="adam",
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )

    history = model.fit(
        x_train,
        y_train,
        validation_data=(x_val, y_val),
        epochs=epochs,
        batch_size=batch_size,
        verbose=1,
    )
    return model, history
