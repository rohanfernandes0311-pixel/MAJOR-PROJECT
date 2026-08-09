"""Live rainfall integration with OpenWeatherMap + simulation fallback."""

from __future__ import annotations

import os
from datetime import datetime

import requests


OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"


def simulated_rainfall_mm(latitude: float, longitude: float) -> float:
    """Deterministic simulation tied to coordinates for demo repeatability."""
    seed_val = abs(int(latitude * 1000) + int(longitude * 1000))
    return float(20 + (seed_val % 140))


def fetch_rainfall_mm(latitude: float, longitude: float) -> dict:
    """
    Returns rainfall context:
      {
        'rainfall_mm': float,
        'source': 'openweathermap'|'simulated',
        'timestamp': iso string,
        'internet_ok': bool
      }
    """
    api_key = os.getenv("OPENWEATHER_API_KEY", "").strip()
    timestamp = datetime.utcnow().isoformat()

    if not api_key:
        return {
            "rainfall_mm": simulated_rainfall_mm(latitude, longitude),
            "source": "simulated",
            "timestamp": timestamp,
            "internet_ok": False,
        }

    params = {
        "lat": latitude,
        "lon": longitude,
        "appid": api_key,
        "units": "metric",
    }
    try:
        response = requests.get(OPENWEATHER_URL, params=params, timeout=8)
        response.raise_for_status()
        data = response.json()
        rain_obj = data.get("rain", {})
        rainfall_mm = float(rain_obj.get("1h", rain_obj.get("3h", 0.0)))
        return {
            "rainfall_mm": rainfall_mm,
            "source": "openweathermap",
            "timestamp": timestamp,
            "internet_ok": True,
        }
    except Exception:
        return {
            "rainfall_mm": simulated_rainfall_mm(latitude, longitude),
            "source": "simulated",
            "timestamp": timestamp,
            "internet_ok": False,
        }
