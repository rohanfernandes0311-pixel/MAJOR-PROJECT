"""Authenticated environmental display data, isolated from ML and Weatherbit."""
from fastapi import APIRouter, Depends, HTTPException, Query, Response

from backend.auth.dependencies import require_auth
from services.smap_environment import SmapUnavailable, UNAVAILABLE, smap_service
from services.imerg_environment import ImergUnavailable, imerg_service

router = APIRouter(prefix="/citizen/environment", tags=["Citizen environment"])


@router.get("/current")
def current_environment(
    response: Response,
    latitude: float = Query(..., ge=-90, le=90, allow_inf_nan=False),
    longitude: float = Query(..., ge=-180, le=180, allow_inf_nan=False),
    _: dict = Depends(require_auth),
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    try:
        return smap_service.fetch(latitude, longitude)
    except SmapUnavailable:
        raise HTTPException(status_code=503, detail=UNAVAILABLE, headers={"Cache-Control": "no-store"}) from None


@router.get("/precipitation")
def current_precipitation(
    response: Response,
    latitude: float = Query(..., ge=-90, le=90, allow_inf_nan=False),
    longitude: float = Query(..., ge=-180, le=180, allow_inf_nan=False),
    _: dict = Depends(require_auth),
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    try:
        return imerg_service.fetch(latitude, longitude)
    except ImergUnavailable:
        raise HTTPException(status_code=503, detail=UNAVAILABLE, headers={"Cache-Control": "no-store"}) from None
