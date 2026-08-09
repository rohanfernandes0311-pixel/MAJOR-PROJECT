"""Lazy extension loader for the LandSense extension layer.

The loader centralizes optional import handling so future services can be
added without creating circular dependencies or touching the core app.
Each component is only instantiated when explicitly requested.
"""

from __future__ import annotations

import importlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .ai_hybrid_extension import HybridModelService
from .anomaly_detection_service import AnomalyDetectionService
from .historical_data_service import HistoricalDataService
from .offline_cache_service import OfflineCacheService
from .prediction_orchestrator import PredictionOrchestrator
from .satellite_service import SatelliteFeatureService
from .threshold_config_service import ThresholdConfigService
from .weather_extension import WeatherExtensionService


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class ExtensionLoader:
    base_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parent.parent)
    enabled: bool = True

    def satellite(self) -> SatelliteFeatureService:
        return SatelliteFeatureService(adapters=self._load_adapters(["services.gee_adapter:GEEAdapter", "services.snap_adapter:SNAPAdapter"]))

    def weather(self) -> WeatherExtensionService:
        return WeatherExtensionService()

    def thresholds(self) -> ThresholdConfigService:
        json_path = self.base_dir / "config" / "thresholds.json"
        sqlite_path = self.base_dir / "data" / "thresholds.db"
        return ThresholdConfigService(json_path=json_path if json_path.exists() else None, sqlite_path=sqlite_path if sqlite_path.exists() else None)

    def offline_cache(self, namespace: str = "landsense") -> OfflineCacheService:
        storage_dir = self.base_dir / "data" / "offline_cache"
        return OfflineCacheService(storage_dir=storage_dir, namespace=namespace)

    def historical(self) -> HistoricalDataService:
        return HistoricalDataService(base_dir=self.base_dir)

    def anomaly(self) -> AnomalyDetectionService:
        return AnomalyDetectionService()

    def hybrid(self) -> HybridModelService:
        return HybridModelService()

    def orchestrator(self) -> PredictionOrchestrator:
        return PredictionOrchestrator(
            threshold_service=self.thresholds(),
            weather_service=self.weather(),
            anomaly_service=self.anomaly(),
            cache_service=self.offline_cache(),
            hybrid_service=self.hybrid(),
        )

    def is_enabled(self, feature_name: str, default: bool = False) -> bool:
        return _env_flag(f"LANDSENSE_ENABLE_{feature_name.upper()}", default)

    def _load_adapters(self, import_specs: list[str]) -> list[Any]:
        adapters: list[Any] = []
        for spec in import_specs:
            try:
                module_name, symbol_name = spec.split(":", 1)
                module = importlib.import_module(module_name)
                symbol = getattr(module, symbol_name)
                adapters.append(symbol())
            except Exception:
                continue
        return adapters
