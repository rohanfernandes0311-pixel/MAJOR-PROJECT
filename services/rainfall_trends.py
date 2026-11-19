"""Display-only rainfall history and forecast providers.

This module is deliberately isolated from the legacy prediction feature path.
Missing observations are represented as null and are never accumulated as zero.
"""
from __future__ import annotations

import math
import os
import threading
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

import requests

POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
WEATHERBIT_FORECAST_URL = "https://api.weatherbit.io/v2.0/forecast/daily"
POWER_SOURCE = "NASA POWER IMERG_PRECTOT (satellite estimate)"
FORECAST_SOURCE = "Weatherbit daily forecast"
POWER_RESOLUTION = "0.1° (~10 km)"
MAX_TREND_DAYS = 1825
MAX_FORECAST_DAYS = 16
TREND_TTL = 6 * 60 * 60
FORECAST_TTL = 30 * 60
FAILURE_TTL = 5 * 60
_lock = threading.Lock()
_cache: dict[tuple[Any, ...], tuple[float, dict[str, Any]]] = {}


class RainfallUnavailable(Exception):
    pass


def _valid_coordinates(latitude: float, longitude: float) -> bool:
    return (isinstance(latitude, (int, float)) and not isinstance(latitude, bool)
            and math.isfinite(latitude) and -90 <= latitude <= 90
            and isinstance(longitude, (int, float)) and not isinstance(longitude, bool)
            and math.isfinite(longitude) and -180 <= longitude <= 180)


def _cached(key: tuple[Any, ...], ttl: int, fetch):
    now = time.monotonic()
    with _lock:
        entry = _cache.get(key)
        if entry and entry[0] > now:
            return dict(entry[1])
    try:
        value = fetch()
    except RainfallUnavailable:
        with _lock:
            _cache[key] = (now + FAILURE_TTL, {"available": False, "records": []})
        raise
    with _lock:
        if len(_cache) >= 256:
            expired = [k for k, v in _cache.items() if v[0] <= now]
            for old in expired:
                _cache.pop(old, None)
            while len(_cache) >= 256:
                _cache.pop(next(iter(_cache)))
        _cache[key] = (now + ttl, dict(value))
    return value


def _date_window(days: int, today: date | None = None) -> tuple[date, date]:
    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= MAX_TREND_DAYS:
        raise ValueError("days must be between 1 and 1825")
    today = today or datetime.now(timezone.utc).date()
    # Exclude the most recent 105 days because NASA POWER warns the period can
    # mix preliminary IMERG Late Run with finalized IMERG data.
    end = today - timedelta(days=105)
    return end - timedelta(days=days - 1), end


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    if not math.isfinite(result) or result < 0 or result > 2000 or result <= -900:
        return None
    return result


def parse_power(payload: Any) -> list[dict[str, Any]]:
    try:
        properties = payload["properties"]
        parameter = properties["parameter"]["IMERG_PRECTOT"]
        records = []
        for key, raw in parameter.items():
            parsed_date = datetime.strptime(key, "%Y%m%d").date().isoformat()
            records.append({"date": parsed_date, "rainfall_mm": _number(raw)})
        return sorted(records, key=lambda record: record["date"])
    except (KeyError, TypeError, ValueError, AttributeError):
        raise RainfallUnavailable() from None


def accumulation_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Return complete 7/30-day totals ending at the latest returned date."""
    valid_dates = [date.fromisoformat(item["date"]) for item in records]
    if not valid_dates:
        return {"latest_date": None, "seven_day_mm": None, "seven_day_coverage": 0,
                "thirty_day_mm": None, "thirty_day_coverage": 0}
    latest = max(valid_dates)
    by_date = {date.fromisoformat(item["date"]): item.get("rainfall_mm") for item in records}
    result: dict[str, Any] = {"latest_date": latest.isoformat()}
    for label, count in (("seven_day", 7), ("thirty_day", 30)):
        expected_days = [latest - timedelta(days=offset) for offset in range(count)]
        values = [by_date.get(day) for day in expected_days]
        coverage = sum(value is not None for value in values)
        result[f"{label}_mm"] = round(sum(values), 2) if coverage == count else None
        result[f"{label}_coverage"] = coverage
    return result


def aggregate_records(records: list[dict[str, Any]], period: str) -> list[dict[str, Any]]:
    """Aggregate daily points; any incomplete bucket remains unavailable."""
    if period not in {"daily", "weekly", "monthly"}:
        raise ValueError("period must be daily, weekly, or monthly")
    if period == "daily":
        return [dict(item) for item in records]
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in records:
        day = date.fromisoformat(item["date"])
        if period == "weekly":
            monday = day - timedelta(days=day.weekday())
            key = monday.isoformat()
        else:
            key = day.strftime("%Y-%m")
        groups.setdefault(key, []).append(item)
    output = []
    for key, values in sorted(groups.items()):
        count = len(values)
        observed = [x["rainfall_mm"] for x in values if x.get("rainfall_mm") is not None]
        if period == "weekly":
            expected = 7
        else:
            first = date.fromisoformat(key + "-01")
            next_month = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
            expected = (next_month - timedelta(days=1)).day
        complete = count == expected and len(observed) == count
        output.append({"date": key, "rainfall_mm": round(sum(observed), 2) if complete else None,
                       "coverage_days": len(observed), "period_days": count})
    return output


def fetch_trends(latitude: float, longitude: float, days: int = 365) -> dict[str, Any]:
    if not _valid_coordinates(latitude, longitude):
        raise ValueError("Invalid coordinates")
    start, end = _date_window(days)
    key = ("power", float(latitude), float(longitude), days, end.isoformat())

    def fetch():
        try:
            response = requests.get(POWER_URL, params={
                "parameters": "IMERG_PRECTOT", "community": "HY",
                "longitude": longitude, "latitude": latitude,
                "start": start.strftime("%Y%m%d"), "end": end.strftime("%Y%m%d"),
                "format": "JSON", "time-standard": "UTC",
            }, timeout=(4, 20), allow_redirects=False)
            if response.status_code != 200:
                raise RainfallUnavailable()
            records = parse_power(response.json())
            return {"available": True, "records": records,
                    "accumulation": accumulation_summary(records),
                    "source": POWER_SOURCE, "unit": "mm/day",
                    "resolution": POWER_RESOLUTION, "time_standard": "UTC",
                    "attribution_url": "https://power.larc.nasa.gov/",
                    "requested_start": start.isoformat(), "requested_end": end.isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "note": "Daily satellite precipitation estimate; latest 105 days excluded for consistent trend analysis."}
        except (requests.RequestException, ValueError, TypeError, RainfallUnavailable):
            raise RainfallUnavailable() from None

    return _cached(key, TREND_TTL, fetch)


def parse_forecast(payload: Any) -> list[dict[str, Any]]:
    try:
        source = payload["data"]
        if not isinstance(source, list) or not 1 <= len(source) <= MAX_FORECAST_DAYS:
            raise ValueError
        output = []
        seen = set()
        for item in source:
            if not isinstance(item, dict):
                raise ValueError
            day = date.fromisoformat(item["valid_date"]).isoformat()
            value = _number(item.get("precip"))
            if value is None or day in seen:
                raise ValueError
            seen.add(day)
            output.append({"date": day, "rainfall_mm": round(value, 1)})
        return sorted(output, key=lambda item: item["date"])
    except (KeyError, TypeError, ValueError):
        raise RainfallUnavailable() from None


def fetch_forecast(latitude: float, longitude: float) -> dict[str, Any]:
    if not _valid_coordinates(latitude, longitude):
        raise ValueError("Invalid coordinates")
    api_key = os.getenv("WEATHERBIT_API_KEY", "").strip()
    if not api_key:
        raise RainfallUnavailable()
    key = ("weatherbit", float(latitude), float(longitude))

    def fetch():
        try:
            response = requests.get(WEATHERBIT_FORECAST_URL, params={
                "lat": latitude, "lon": longitude, "days": MAX_FORECAST_DAYS,
                "units": "M", "key": api_key,
            }, timeout=(3.05, 8), allow_redirects=False)
            if response.status_code != 200:
                raise RainfallUnavailable()
            records = parse_forecast(response.json())
            if api_key in str(response.text):
                raise RainfallUnavailable()
            return {"available": True, "records": records, "source": FORECAST_SOURCE,
                    "unit": "mm/day", "updated_at": datetime.now(timezone.utc).isoformat(),
                    "forecast_start": records[0]["date"], "forecast_end": records[-1]["date"],
                    "attribution_url": "https://www.weatherbit.io/",
                    "note": "Forecast values are model guidance, not confirmed rainfall or landslide predictions."}
        except (requests.RequestException, ValueError, TypeError, RainfallUnavailable):
            raise RainfallUnavailable() from None

    return _cached(key, FORECAST_TTL, fetch)
