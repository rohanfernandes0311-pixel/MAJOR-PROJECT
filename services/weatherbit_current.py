"""Weatherbit-only current conditions for display; no prediction inputs or cache."""

from __future__ import annotations

import math
import os
from datetime import datetime, timezone
from typing import Any

import requests


CURRENT_WEATHER_URL = "https://api.weatherbit.io/v2.0/current"
UNAVAILABLE = "Live weather unavailable."


class WeatherbitUnavailable(Exception):
    """Safe failure message, without upstream URLs, bodies, or credentials."""

    def __init__(self) -> None:
        super().__init__(UNAVAILABLE)


def _number(value: Any, minimum: float | None = None, maximum: float | None = None) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value):
        return None
    if minimum is not None and value < minimum:
        return None
    if maximum is not None and value > maximum:
        return None
    return float(value)


def _observation_time(observation: dict[str, Any]) -> str | None:
    timestamp = _number(observation.get("ts"), minimum=0)
    try:
        if timestamp is not None:
            return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()
        value = observation.get("ob_time")
        if isinstance(value, str) and value.strip():
            observed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            if observed.tzinfo is None:
                observed = observed.replace(tzinfo=timezone.utc)
            return observed.astimezone(timezone.utc).isoformat()
    except (ValueError, OverflowError, OSError):
        pass
    return None


def fetch_current_weather(latitude: float, longitude: float) -> dict[str, Any]:
    """Fetch only the supplied coordinates. Missing measurements remain None."""
    if _number(latitude, -90, 90) is None or _number(longitude, -180, 180) is None:
        raise WeatherbitUnavailable()
    api_key = os.getenv("WEATHERBIT_API_KEY", "").strip()
    if not api_key:
        raise WeatherbitUnavailable()
    try:
        response = requests.get(
            CURRENT_WEATHER_URL,
            params={"lat": latitude, "lon": longitude, "units": "M", "key": api_key},
            timeout=(3.05, 8),
            allow_redirects=False,
        )
        if response.status_code != 200:
            raise WeatherbitUnavailable()
        payload = response.json()
        observations = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(observations, list) or not observations or not isinstance(observations[0], dict):
            raise WeatherbitUnavailable()
        observation = observations[0]
        conditions = observation.get("weather")
        description = conditions.get("description") if isinstance(conditions, dict) else None
        description = description.strip() if isinstance(description, str) else None
        if description and api_key in description:
            raise WeatherbitUnavailable()
        weather = {
            "source": "weatherbit",
            "temperature_c": _number(observation.get("temp")),
            "humidity_pct": _number(observation.get("rh"), 0, 100),
            "wind_speed_mps": _number(observation.get("wind_spd"), 0),
            "visibility_km": _number(observation.get("vis"), 0),
            "precipitation_mm_per_hour": _number(observation.get("precip"), 0),
            "description": description or None,
            "observed_at": _observation_time(observation),
        }
        if not any(weather[field] is not None for field in (
            "temperature_c", "humidity_pct", "wind_speed_mps", "visibility_km",
            "precipitation_mm_per_hour", "description",
        )):
            raise WeatherbitUnavailable()
        return weather
    except (requests.RequestException, ValueError, TypeError, OverflowError):
        raise WeatherbitUnavailable() from None
