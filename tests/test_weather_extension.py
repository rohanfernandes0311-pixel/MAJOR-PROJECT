"""Focused Phase 5.2 tests for provider quality, fallback, and caching."""

from __future__ import annotations

import unittest
from typing import Any

from services.weather_extension import WeatherExtensionService


class StaticProvider:
    name = "test_provider"

    def __init__(self, payload: dict[str, Any] | None) -> None:
        self.payload = payload
        self.calls = 0

    def fetch(self, latitude: float, longitude: float) -> dict[str, Any] | None:
        self.calls += 1
        return self.payload


class WeatherExtensionTests(unittest.TestCase):
    def test_valid_provider_response_is_real_and_has_quality_metadata(self) -> None:
        provider = StaticProvider({"rainfall_mm": 12.5, "observed_at": "2026-08-14T10:00:00+00:00"})
        result = WeatherExtensionService(providers=[provider]).fetch_rainfall_mm(18.4, 73.2)

        self.assertEqual(result["provider"], "test_provider")
        self.assertEqual(result["source"], "real")
        self.assertEqual(result["source_type"], "real")
        self.assertEqual(result["rainfall_mm"], 12.5)
        self.assertEqual(result["observed_at"], "2026-08-14T10:00:00+00:00")
        self.assertIn("timestamp", result)

    def test_provider_failure_uses_explicit_synthetic_fallback(self) -> None:
        result = WeatherExtensionService(providers=[StaticProvider(None)], allow_simulated_fallback=True).fetch_rainfall_mm(18.4, 73.2)

        self.assertEqual(result["provider"], "synthetic_coordinate_fallback")
        self.assertEqual(result["source"], "simulated")
        self.assertEqual(result["source_type"], "simulated")
        self.assertGreaterEqual(result["rainfall_mm"], 0)

    def test_all_providers_unavailable_can_return_no_rainfall(self) -> None:
        result = WeatherExtensionService(providers=[StaticProvider(None)], allow_simulated_fallback=False).fetch_rainfall_mm(18.4, 73.2)

        self.assertIsNone(result["provider"])
        self.assertEqual(result["source"], "unavailable")
        self.assertEqual(result["source_type"], "unavailable")
        self.assertEqual(result["rainfall_mm"], 0.0)

    def test_synthetic_fallback_only_marks_rainfall_as_available(self) -> None:
        result = WeatherExtensionService(providers=[StaticProvider(None)], allow_simulated_fallback=True).fetch_weather_context(18.4, 73.2)

        self.assertEqual(result["source_type"], "simulated")
        self.assertEqual(result["available_fields"], ["rainfall_mm"])

    def test_provider_field_availability_is_preserved(self) -> None:
        provider = StaticProvider({"rainfall_mm": 8.0, "available_fields": ["rainfall_mm"]})
        result = WeatherExtensionService(providers=[provider]).fetch_weather_context(18.4, 73.2)

        self.assertEqual(result["source_type"], "real")
        self.assertEqual(result["available_fields"], ["rainfall_mm"])

    def test_weather_cache_reuses_provider_snapshot(self) -> None:
        provider = StaticProvider({"rainfall_mm": 3.0})
        service = WeatherExtensionService(providers=[provider])

        first = service.fetch_weather_context(18.4, 73.2)
        second = service.fetch_weather_context(18.4, 73.2)

        self.assertFalse(first["cache_hit"])
        self.assertTrue(second["cache_hit"])
        self.assertEqual(provider.calls, 1)


if __name__ == "__main__":
    unittest.main()
