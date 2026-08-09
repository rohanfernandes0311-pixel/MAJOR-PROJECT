"""Backward-compatible prediction orchestrator.

This wrapper composes the existing prediction engine with optional
extensions. It does not replace the core models; instead, it annotates
and enriches outputs when those extensions are enabled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .ai_hybrid_extension import HybridModelService
from .anomaly_detection_service import AnomalyDetectionService
from .offline_cache_service import OfflineCacheService
from .threshold_config_service import ThresholdConfigService
from .weather_extension import WeatherExtensionService


@dataclass(slots=True)
class PredictionOrchestrator:
    threshold_service: ThresholdConfigService | None = None
    weather_service: WeatherExtensionService | None = None
    anomaly_service: AnomalyDetectionService | None = None
    cache_service: OfflineCacheService | None = None
    hybrid_service: HybridModelService | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.threshold_service = self.threshold_service or ThresholdConfigService()
        self.weather_service = self.weather_service or WeatherExtensionService()
        self.anomaly_service = self.anomaly_service or AnomalyDetectionService()
        self.hybrid_service = self.hybrid_service or HybridModelService()

    def enrich_features(
        self,
        *,
        latitude: float,
        longitude: float,
        feature_payload: dict[str, Any],
        region: str | None = None,
        include_weather: bool = True,
    ) -> dict[str, Any]:
        enriched = dict(feature_payload)
        if include_weather and self.weather_service is not None:
            enriched.setdefault("weather", self.weather_service.fetch_rainfall_mm(latitude, longitude))
        if self.threshold_service is not None:
            enriched.setdefault("thresholds", self.threshold_service.load(region))
        return enriched

    def predict_hybrid(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        if self.hybrid_service is None:
            raise RuntimeError("Hybrid service unavailable")
        model = kwargs.pop("model", "hybrid")
        return self.hybrid_service.predict_single(*args, model=model, **kwargs)

    def score_anomalies(self, features: np.ndarray) -> dict[str, Any]:
        if self.anomaly_service is None:
            return {"method": "unavailable", "anomaly_flags": [], "anomaly_scores": []}
        return self.anomaly_service.score(features)

    def persist_prediction(self, prediction: dict[str, Any], region: str | None = None) -> dict[str, Any] | None:
        if self.cache_service is None:
            return None
        return self.cache_service.persist_prediction(prediction, region=region)

    def sync_pending(self) -> list[dict[str, Any]]:
        if self.cache_service is None:
            return []
        return self.cache_service.flush()
