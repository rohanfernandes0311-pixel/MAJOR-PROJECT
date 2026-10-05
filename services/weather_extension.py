"""Optional weather extension layer with provider fallbacks.

This module preserves the existing OpenWeatherMap fallback behavior while
adding optional provider hooks for IMD, NASA POWER, WeatherAPI, and future
providers. Each provider is isolated behind a defensive adapter so failures
never interrupt the core system.
"""

from __future__ import annotations

import os
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

import requests

from rainfall_service import simulated_rainfall_mm


class WeatherProvider(Protocol):
    name: str

    def fetch(self, latitude: float, longitude: float) -> dict[str, Any] | None:
        ...


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


SOURCE_REAL = "real"
SOURCE_SIMULATED = "simulated"
SOURCE_UNAVAILABLE = "unavailable"
SOURCE_TYPES = {SOURCE_REAL, SOURCE_SIMULATED, SOURCE_UNAVAILABLE}


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class OpenWeatherProvider:
    name: str = "openweathermap"

    def fetch(self, latitude: float, longitude: float) -> dict[str, Any] | None:
        api_key = os.getenv("OPENWEATHER_API_KEY", "").strip()
        if not api_key:
            return None

        try:
            response = requests.get(
                "https://api.openweathermap.org/data/2.5/weather",
                params={"lat": latitude, "lon": longitude, "appid": api_key, "units": "metric"},
                timeout=8,
            )
            response.raise_for_status()
            data = response.json()
            rain_obj = data.get("rain", {})
            main = data.get("main", {})
            wind = data.get("wind", {})
            clouds = data.get("clouds", {})
            weather_items = data.get("weather", [])
            weather_primary = weather_items[0] if weather_items else {}
            rainfall_mm = float(rain_obj.get("1h", rain_obj.get("3h", 0.0)))
            return {
                "rainfall_mm": rainfall_mm,
                "temperature_c": float(main.get("temp", 0.0)),
                "humidity_pct": float(main.get("humidity", 0.0)),
                "wind_speed_mps": float(wind.get("speed", 0.0)),
                "cloud_pct": float(clouds.get("all", 0.0)),
                "weather_main": str(weather_primary.get("main", "")).strip() or "Unknown",
                "weather_description": str(weather_primary.get("description", "")).strip() or "Unknown",
                "storm_indicator": bool(
                    str(weather_primary.get("main", "")).strip().lower() in {"thunderstorm", "tornado"}
                    or float(rainfall_mm) >= 25.0
                    or float(wind.get("speed", 0.0)) >= 12.0
                ),
                "source": self.name,
                "observed_at": datetime.fromtimestamp(
                    float(data.get("dt", datetime.now(timezone.utc).timestamp())), timezone.utc
                ).isoformat(),
                "internet_ok": True,
                "available_fields": ["rainfall_mm"]
                + (["temperature_c"] if "temp" in main else [])
                + (["humidity_pct"] if "humidity" in main else [])
                + (["wind_speed_mps"] if "speed" in wind else [])
                + (["cloud_pct"] if "all" in clouds else []),
            }
        except Exception:
            return None


@dataclass(slots=True)
class WeatherApiProvider:
    name: str = "weatherapi"

    def fetch(self, latitude: float, longitude: float) -> dict[str, Any] | None:
        api_key = os.getenv("WEATHERAPI_KEY", "").strip()
        if not api_key:
            return None

        try:
            response = requests.get(
                "https://api.weatherapi.com/v1/current.json",
                params={"key": api_key, "q": f"{latitude},{longitude}"},
                timeout=8,
            )
            response.raise_for_status()
            data = response.json()
            current = data.get("current", {})
            rainfall_mm = float(current.get("precip_mm", 0.0))
            return {
                "rainfall_mm": rainfall_mm,
                "temperature_c": float(current.get("temp_c", 0.0)),
                "humidity_pct": float(current.get("humidity", 0.0)),
                "wind_speed_mps": float(current.get("wind_kph", 0.0)) / 3.6,
                "cloud_pct": float(current.get("cloud", 0.0)),
                "weather_main": str(current.get("condition", {}).get("text", "")).strip() or "Unknown",
                "weather_description": str(current.get("condition", {}).get("text", "")).strip() or "Unknown",
                "storm_indicator": bool(float(rainfall_mm) >= 25.0 or float(current.get("wind_kph", 0.0)) >= 45.0),
                "source": self.name,
                "observed_at": datetime.fromtimestamp(
                    float(current.get("last_updated_epoch", datetime.now(timezone.utc).timestamp())), timezone.utc
                ).isoformat(),
                "internet_ok": True,
                "available_fields": [
                    field_name
                    for field_name, provider_field in (
                        ("rainfall_mm", "precip_mm"), ("temperature_c", "temp_c"),
                        ("humidity_pct", "humidity"), ("wind_speed_mps", "wind_kph"), ("cloud_pct", "cloud"),
                    )
                    if provider_field in current
                ],
            }
        except Exception:
            return None


@dataclass(slots=True)
class NasaPowerProvider:
    name: str = "nasa_power"

    def fetch(self, latitude: float, longitude: float) -> dict[str, Any] | None:
        endpoint = os.getenv("NASA_POWER_ENDPOINT", "https://power.larc.nasa.gov/api/temporal/daily/point")
        params = {
            "parameters": "PRECTOTCORR",
            "community": "AG",
            "longitude": longitude,
            "latitude": latitude,
            "format": "JSON",
        }
        try:
            response = requests.get(endpoint, params=params, timeout=10)
            response.raise_for_status()
            payload = response.json()
            params_data = payload.get("properties", {}).get("parameter", {})
            rain_series = params_data.get("PRECTOTCORR", {})
            valid_readings: list[tuple[str, float]] = []
            for date, value in rain_series.items():
                try:
                    parsed = float(value)
                    if math.isfinite(parsed) and parsed >= 0:
                        valid_readings.append((str(date), parsed))
                except (TypeError, ValueError):
                    continue
            if not valid_readings:
                return None
            # NASA POWER is daily data. Select its most recent valid daily
            # observation rather than relying on JSON object iteration order.
            observed_date, rainfall_mm = max(valid_readings, key=lambda item: item[0])
            return {
                "rainfall_mm": rainfall_mm,
                "weather_main": "Unknown",
                "weather_description": "Unknown",
                "storm_indicator": bool(rainfall_mm >= 25.0),
                "source": self.name,
                "observed_at": observed_date,
                "internet_ok": True,
                "available_fields": ["rainfall_mm"],
            }
        except Exception:
            return None


@dataclass(slots=True)
class ImdWeatherProvider:
    name: str = "imd"

    def fetch(self, latitude: float, longitude: float) -> dict[str, Any] | None:
        # IMD access is typically deployment-specific. This adapter exists so
        # a concrete integration can be injected later without changing the API.
        endpoint = os.getenv("IMD_WEATHER_ENDPOINT", "").strip()
        if not endpoint:
            return None

        try:
            response = requests.get(endpoint, params={"lat": latitude, "lon": longitude}, timeout=10)
            response.raise_for_status()
            data = response.json()
            rainfall_mm = float(data.get("rainfall_mm", data.get("rainfall", 0.0)))
            return {
                "rainfall_mm": rainfall_mm,
                "temperature_c": float(data.get("temperature_c", 0.0)),
                "humidity_pct": float(data.get("humidity_pct", data.get("humidity", 0.0))),
                "wind_speed_mps": float(data.get("wind_speed_mps", data.get("wind_speed", 0.0))),
                "cloud_pct": float(data.get("cloud_pct", data.get("cloud", 0.0))),
                "weather_main": str(data.get("weather_main", "Unknown")),
                "weather_description": str(data.get("weather_description", "Unknown")),
                "storm_indicator": bool(data.get("storm_indicator", rainfall_mm >= 25.0)),
                "source": self.name,
                "observed_at": str(data.get("timestamp") or data.get("observed_at") or _utc_iso()),
                "internet_ok": True,
                "available_fields": ["rainfall_mm"]
                + (["temperature_c"] if "temperature_c" in data else [])
                + (["humidity_pct"] if "humidity_pct" in data or "humidity" in data else [])
                + (["wind_speed_mps"] if "wind_speed_mps" in data or "wind_speed" in data else [])
                + (["cloud_pct"] if "cloud_pct" in data or "cloud" in data else []),
            }
        except Exception:
            return None


@dataclass(slots=True)
class WeatherExtensionService:
    providers: list[WeatherProvider] | None = None
    cache_ttl_seconds: int = 300
    allow_simulated_fallback: bool = field(
        default_factory=lambda: _env_flag("WEATHER_ALLOW_SIMULATED_FALLBACK", True)
    )
    _cache: dict[str, tuple[float, dict[str, Any]]] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.providers is None:
            self.providers = [ImdWeatherProvider(), NasaPowerProvider(), WeatherApiProvider(), OpenWeatherProvider()]

    def _cache_key(self, latitude: float, longitude: float) -> str:
        return f"{round(latitude, 3)}:{round(longitude, 3)}"

    def _weather_severity(self, snapshot: dict[str, Any]) -> str:
        rainfall = float(snapshot.get("rainfall_mm", 0.0) or 0.0)
        wind_speed = float(snapshot.get("wind_speed_mps", 0.0) or 0.0)
        humidity = float(snapshot.get("humidity_pct", 0.0) or 0.0)
        cloud_pct = float(snapshot.get("cloud_pct", 0.0) or 0.0)
        storm = bool(snapshot.get("storm_indicator", False))

        score = 0
        if rainfall >= 50.0:
            score += 3
        elif rainfall >= 20.0:
            score += 2
        elif rainfall >= 5.0:
            score += 1

        if wind_speed >= 15.0:
            score += 2
        elif wind_speed >= 8.0:
            score += 1

        if humidity >= 85.0:
            score += 1
        if cloud_pct >= 75.0:
            score += 1
        if storm:
            score += 2

        if score >= 5:
            return "high"
        if score >= 3:
            return "moderate"
        return "low"

    @staticmethod
    def _number(value: Any, default: float = 0.0, *, minimum: float | None = None) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return default
        if not math.isfinite(parsed) or (minimum is not None and parsed < minimum):
            return default
        return parsed

    def _finalize(self, snapshot: dict[str, Any], *, cache_hit: bool, cache_age_seconds: int = 0) -> dict[str, Any]:
        """Return the public weather contract without exposing provider credentials."""
        snapshot["source_type"] = snapshot.get("source_type") if snapshot.get("source_type") in SOURCE_TYPES else SOURCE_UNAVAILABLE
        # `source` is deliberately the classification; `provider` identifies
        # the vendor. This prevents a synthetic value being mistaken for data
        # from a real weather provider.
        snapshot["source"] = snapshot["source_type"]
        snapshot["rainfall_mm"] = self._number(snapshot.get("rainfall_mm"), minimum=0.0)
        snapshot["timestamp"] = str(snapshot.get("timestamp") or _utc_iso())
        snapshot["observed_at"] = str(snapshot.get("observed_at") or snapshot["timestamp"])
        snapshot["cache_hit"] = cache_hit
        snapshot["cache_age_seconds"] = cache_age_seconds
        snapshot["weather_severity"] = self._weather_severity(snapshot)
        return snapshot

    def fetch_weather_context(self, latitude: float, longitude: float) -> dict[str, Any]:
        cache_key = self._cache_key(latitude, longitude)
        cached = self._cache.get(cache_key)
        now = datetime.now(timezone.utc).timestamp()
        if cached and (now - cached[0]) <= self.cache_ttl_seconds:
            return self._finalize(dict(cached[1]), cache_hit=True, cache_age_seconds=max(0, int(now - cached[0])))

        for provider in self.providers or []:
            try:
                result = provider.fetch(latitude, longitude)
                if result:
                    snapshot = {
                        "latitude": latitude,
                        "longitude": longitude,
                        "timestamp": _utc_iso(),
                        "provider": result.get("source", provider.name),
                        "observed_at": result.get("observed_at"),
                        "source_type": SOURCE_REAL,
                        "internet_ok": bool(result.get("internet_ok", True)),
                        "rainfall_mm": self._number(result.get("rainfall_mm"), minimum=0.0),
                        "temperature_c": self._number(result.get("temperature_c")),
                        "humidity_pct": self._number(result.get("humidity_pct"), minimum=0.0),
                        "wind_speed_mps": self._number(result.get("wind_speed_mps"), minimum=0.0),
                        "cloud_pct": self._number(result.get("cloud_pct"), minimum=0.0),
                        "weather_main": str(result.get("weather_main", "Unknown") or "Unknown"),
                        "weather_description": str(result.get("weather_description", "Unknown") or "Unknown"),
                        "storm_indicator": bool(result.get("storm_indicator", False)),
                        "available_fields": list(result.get("available_fields") or [
                            field_name
                            for field_name in ("rainfall_mm", "temperature_c", "humidity_pct", "wind_speed_mps", "cloud_pct")
                            if field_name in result
                        ]),
                    }
                    snapshot = self._finalize(snapshot, cache_hit=False)
                    self._cache[cache_key] = (now, snapshot)
                    return dict(snapshot)
            except Exception:
                continue

        if self.allow_simulated_fallback:
            snapshot = {
                "latitude": latitude,
                "longitude": longitude,
                "rainfall_mm": simulated_rainfall_mm(latitude, longitude),
                "temperature_c": 0.0,
                "humidity_pct": 0.0,
                "wind_speed_mps": 0.0,
                "cloud_pct": 0.0,
                "weather_main": "Simulated",
                "weather_description": "Synthetic fallback",
                "storm_indicator": False,
                "provider": "synthetic_coordinate_fallback",
                "source_type": SOURCE_SIMULATED,
                "timestamp": _utc_iso(),
                "internet_ok": False,
                "available_fields": ["rainfall_mm"],
            }
        else:
            snapshot = {
                "latitude": latitude,
                "longitude": longitude,
                "rainfall_mm": 0.0,
                "temperature_c": 0.0,
                "humidity_pct": 0.0,
                "wind_speed_mps": 0.0,
                "cloud_pct": 0.0,
                "weather_main": "Unavailable",
                "weather_description": "No weather provider available",
                "storm_indicator": False,
                "provider": None,
                "source_type": SOURCE_UNAVAILABLE,
                "timestamp": _utc_iso(),
                "internet_ok": False,
                "available_fields": [],
            }
        snapshot = self._finalize(snapshot, cache_hit=False)
        self._cache[cache_key] = (now, snapshot)
        return dict(snapshot)

    def fetch_rainfall_mm(self, latitude: float, longitude: float) -> dict[str, Any]:
        context = self.fetch_weather_context(latitude, longitude)
        return {
            "rainfall_mm": context.get("rainfall_mm", 0.0),
            "provider": context.get("provider"),
            "source": context.get("source", SOURCE_UNAVAILABLE),
            "source_type": context.get("source_type", SOURCE_UNAVAILABLE),
            "timestamp": context.get("timestamp", _utc_iso()),
            "observed_at": context.get("observed_at", context.get("timestamp", _utc_iso())),
            "cache_hit": context.get("cache_hit", False),
            "cache_age_seconds": context.get("cache_age_seconds", 0),
            "internet_ok": context.get("internet_ok", False),
            "temperature_c": context.get("temperature_c", 0.0),
            "humidity_pct": context.get("humidity_pct", 0.0),
            "wind_speed_mps": context.get("wind_speed_mps", 0.0),
            "cloud_pct": context.get("cloud_pct", 0.0),
            "weather_main": context.get("weather_main", "Unknown"),
            "weather_description": context.get("weather_description", "Unknown"),
            "storm_indicator": context.get("storm_indicator", False),
            "weather_severity": context.get("weather_severity", "low"),
            "available_fields": list(context.get("available_fields") or []),
        }
