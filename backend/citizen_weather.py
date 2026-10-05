"""Authenticated display-only Citizen weather, independent of predictions."""

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from backend.auth.dependencies import require_auth
from services.weatherbit_current import UNAVAILABLE, WeatherbitUnavailable, fetch_current_weather


router = APIRouter(prefix="/citizen/weather", tags=["Citizen weather"])


@router.get("/current")
def current_weather(
    response: Response,
    latitude: float = Query(..., ge=-90, le=90, allow_inf_nan=False),
    longitude: float = Query(..., ge=-180, le=180, allow_inf_nan=False),
    _: dict = Depends(require_auth),
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    try:
        return fetch_current_weather(latitude, longitude)
    except WeatherbitUnavailable:
        raise HTTPException(status_code=503, detail=UNAVAILABLE, headers={"Cache-Control": "no-store"}) from None
