"""Authenticated rainfall history and forecast display endpoints."""
from fastapi import APIRouter, Depends, Query, Response

from backend.auth.dependencies import require_auth
from services.rainfall_trends import (
    RainfallUnavailable, aggregate_records, fetch_forecast, fetch_trends,
)

router = APIRouter(prefix="/citizen/rainfall", tags=["Citizen rainfall"])


@router.get("/trends")
def rainfall_trends(
    response: Response,
    latitude: float = Query(..., ge=-90, le=90, allow_inf_nan=False),
    longitude: float = Query(..., ge=-180, le=180, allow_inf_nan=False),
    days: int = Query(365, ge=1, le=1825),
    period: str = Query("daily", pattern="^(daily|weekly|monthly)$"),
    _: dict = Depends(require_auth),
) -> dict:
    response.headers["Cache-Control"] = "private, max-age=300"
    try:
        result = fetch_trends(latitude, longitude, days)
        if not result.get("available"):
            return {"available": False, "records": [], "source": result.get("source")}
        result["records"] = aggregate_records(result["records"], period)
        result["period"] = period
        result["unit"] = "mm/day" if period == "daily" else "mm/period"
        return result
    except RainfallUnavailable:
        return {"available": False, "records": [], "source": "NASA POWER IMERG_PRECTOT"}


@router.get("/forecast")
def rainfall_forecast(
    response: Response,
    latitude: float = Query(..., ge=-90, le=90, allow_inf_nan=False),
    longitude: float = Query(..., ge=-180, le=180, allow_inf_nan=False),
    _: dict = Depends(require_auth),
) -> dict:
    response.headers["Cache-Control"] = "private, max-age=300"
    try:
        return fetch_forecast(latitude, longitude)
    except RainfallUnavailable:
        return {"available": False, "records": [], "source": "Weatherbit daily forecast"}
