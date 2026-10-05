"""Backend-authoritative Phase 6 explainable Admin intelligence."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from geofencing import point_in_polygon


RISK_LEVELS = {"SAFE", "LOW", "MEDIUM", "HIGH", "CRITICAL"}
SOURCE_STATES = {"REAL", "SIMULATED", "UNAVAILABLE"}
WEATHER_FIELDS = (
    ("rainfall", "rainfall_mm", "mm"),
    ("temperature", "temperature_c", "°C"),
    ("humidity", "humidity_pct", "%"),
    ("wind", "wind_speed_mps", "m/s"),
)


def polygon_centroid(feature: dict[str, Any]) -> tuple[float, float]:
    coordinates = feature.get("geometry", {}).get("coordinates", [])
    ring = coordinates[0] if coordinates else []
    points = ring[:-1] if len(ring) > 1 and ring[0] == ring[-1] else ring
    if not points:
        raise ValueError("Configured zone geometry is unavailable")
    longitude = sum(float(point[0]) for point in points) / len(points)
    latitude = sum(float(point[1]) for point in points) / len(points)
    return latitude, longitude


def normalize_risk(value: Any, *, default: str | None = None) -> str | None:
    normalized = str(value or "").upper()
    if normalized in RISK_LEVELS:
        return normalized
    return default


def load_incident_catalog(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, list):
        raise ValueError("Incident catalog must be a list")
    required = {"id", "title", "date", "latitude", "longitude", "location_precision", "demo_risk", "verification_status"}
    for incident in payload:
        if not isinstance(incident, dict) or not required.issubset(incident):
            raise ValueError("Incident catalog record is incomplete")
        if incident["verification_status"] not in {"verified", "source_review_required"}:
            raise ValueError("Incident verification status is invalid")
        if normalize_risk(incident["demo_risk"]) is None:
            raise ValueError("Incident demo risk is invalid")
    return payload


def find_incident_for_zone(feature: dict[str, Any], incidents: list[dict[str, Any]]) -> dict[str, Any] | None:
    rings = feature.get("geometry", {}).get("coordinates", [])
    ring = rings[0] if rings else []
    matches = [
        incident for incident in incidents
        if point_in_polygon(float(incident["latitude"]), float(incident["longitude"]), ring)
    ]
    return max(matches, key=lambda item: str(item.get("date", "")), default=None)


def _weather_values(weather: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    snapshot = weather or {}
    source = str(snapshot.get("source_type") or snapshot.get("source") or "unavailable").upper()
    source = source if source in SOURCE_STATES else "UNAVAILABLE"
    available = set(snapshot.get("available_fields") or [])
    return {
        label: {
            "value": snapshot.get(field) if source != "UNAVAILABLE" and field in available else None,
            "unit": unit,
            "status": source if source != "UNAVAILABLE" and field in available else "UNAVAILABLE",
        }
        for label, field, unit in WEATHER_FIELDS
    }


def _impact_for_risk(risk: str | None) -> str:
    if risk in {"HIGH", "CRITICAL"}:
        return "ELEVATED"
    if risk == "MEDIUM":
        return "SUPPORTING"
    if risk in {"SAFE", "LOW"}:
        return "NEUTRAL"
    return "UNKNOWN"


def _factor(name: str, status: str, impact: str, available: bool, explanation: str, **values: Any) -> dict[str, Any]:
    return {"factor": name, "status": status, "impact": impact, "available": available, "explanation": explanation, **values}


def _assessment_factors(
    *,
    weather: dict[str, Any] | None,
    environmental_values: dict[str, dict[str, Any]],
    historical_count: int | None,
    historical_available: bool,
    incident: dict[str, Any] | None,
    incident_catalog_available: bool,
    ml_risk: str | None,
    ml_confidence: float | None,
    configured_risk: str,
) -> list[dict[str, Any]]:
    rainfall = environmental_values["rainfall"]
    severity = str((weather or {}).get("weather_severity") or "").upper()
    rainfall_status = {"HIGH": "HIGH", "MODERATE": "MEDIUM", "LOW": "LOW"}.get(severity, "UNKNOWN")
    rainfall_available = rainfall["status"] != "UNAVAILABLE"
    rainfall_explanation = (
        "High rainfall conditions are contributing to elevated landslide susceptibility."
        if rainfall_status == "HIGH" else
        "Moderate rainfall conditions provide supporting landslide-risk context."
        if rainfall_status == "MEDIUM" else
        "Available rainfall conditions are not classified as elevated by the existing weather logic."
        if rainfall_available else
        "Rainfall data is unavailable and was not used as evidence."
    )
    factors = [_factor(
        "rainfall", rainfall_status, "ELEVATED" if rainfall_status in {"HIGH", "MEDIUM"} else "NEUTRAL" if rainfall_available else "UNKNOWN",
        rainfall_available, rainfall_explanation, value=rainfall["value"], unit=rainfall["unit"], source=rainfall["status"],
    )]

    for name in ("humidity", "temperature", "wind"):
        item = environmental_values[name]
        available = item["status"] != "UNAVAILABLE"
        factors.append(_factor(
            name, "AVAILABLE" if available else "UNKNOWN", "SUPPORTING" if available else "UNKNOWN", available,
            f"{name.title()} is available as environmental context; no independent mathematical weight is applied."
            if available else f"{name.title()} data is unavailable and was not used as evidence.",
            value=item["value"], unit=item["unit"], source=item["status"],
        ))

    if historical_available:
        count = int(historical_count or 0)
        factors.append(_factor(
            "historical_activity", "PRESENT" if count else "NONE_IDENTIFIED", "SUPPORTING" if count else "NEUTRAL", True,
            f"{count} historical landslide record{'s' if count != 1 else ''} were found within the configured zone."
            if count else "No historical landslide records were found within the configured zone; this is not evidence that the area is safe.",
            value=count, unit="records", classification="HISTORICAL INVENTORY",
        ))
    else:
        factors.append(_factor("historical_activity", "UNKNOWN", "UNKNOWN", False, "Historical inventory is unavailable and was not used as evidence.", value=None, unit="records"))

    if not incident_catalog_available:
        factors.append(_factor("recent_incident", "UNKNOWN", "UNKNOWN", False, "Recent incident context is unavailable.", value=None, unit=None))
    elif incident:
        verified = incident.get("verification_status") == "verified"
        factors.append(_factor(
            "recent_incident", "VERIFIED" if verified else "DEMO_SCENARIO", "ELEVATED" if verified else "SUPPORTING", True,
            "A verified recent incident is associated with this configured zone."
            if verified else "A source-review-required demo incident scenario is associated with this configured zone; it is not an official live risk classification.",
            value="YES", unit=None, verificationStatus=incident.get("verification_status"),
            classification=f"{normalize_risk(incident.get('demo_risk'), default='HIGH')} — DEMO CLASSIFICATION",
        ))
    else:
        factors.append(_factor("recent_incident", "NONE_IDENTIFIED", "NEUTRAL", True, "No curated recent incident was matched to this zone; absence is not evidence of safety.", value="NO", unit=None))

    factors.append(_factor(
        "ml_prediction", ml_risk or "UNKNOWN", _impact_for_risk(ml_risk), ml_risk is not None,
        f"The existing ML model predicts {ml_risk}." if ml_risk else "No persisted ML prediction is available for this zone.",
        value=ml_risk, unit=None, confidence=ml_confidence, authority="EXISTING ML PREDICTION",
    ))
    factors.append(_factor(
        "configured_zone", configured_risk, _impact_for_risk(configured_risk), True,
        f"The configured zone classification is {configured_risk}.", value=configured_risk, unit=None,
    ))
    return factors


def _data_quality(weather_source: str, historical_available: bool, ml_available: bool, incident_catalog_available: bool) -> str:
    available_count = sum((weather_source != "UNAVAILABLE", historical_available, ml_available, incident_catalog_available))
    if available_count == 4 and weather_source == "REAL":
        return "GOOD"
    if available_count >= 3:
        return "PARTIAL"
    if available_count >= 1:
        return "LIMITED"
    return "UNAVAILABLE"


def build_zone_intelligence(
    feature: dict[str, Any], *, weather: dict[str, Any] | None, historical_count: int | None,
    historical_available: bool, ml_risk: str | None, ml_confidence: float | None = None,
    overall_risk: str | None = None, incident: dict[str, Any] | None = None,
    incident_catalog_available: bool = True,
) -> dict[str, Any]:
    properties = feature.get("properties", {})
    latitude, longitude = polygon_centroid(feature)
    configured_risk = normalize_risk(properties.get("risk_level"))
    if configured_risk is None:
        raise ValueError("Configured zone risk is invalid")
    normalized_ml = normalize_risk(ml_risk)
    normalized_overall = normalize_risk(overall_risk, default=normalized_ml or configured_risk) or configured_risk
    confidence = float(ml_confidence) if isinstance(ml_confidence, (int, float)) and math.isfinite(float(ml_confidence)) and 0 <= float(ml_confidence) <= 1 else None
    weather_source = str((weather or {}).get("source_type") or (weather or {}).get("source") or "unavailable").upper()
    weather_source = weather_source if weather_source in SOURCE_STATES else "UNAVAILABLE"
    environmental_values = _weather_values(weather)
    factors = _assessment_factors(
        weather=weather, environmental_values=environmental_values, historical_count=historical_count,
        historical_available=historical_available, incident=incident, incident_catalog_available=incident_catalog_available,
        ml_risk=normalized_ml, ml_confidence=confidence, configured_risk=configured_risk,
    )
    recommendation = {"SAFE": "MONITOR", "LOW": "MONITOR", "MEDIUM": "PREPARE_WARNING", "HIGH": "PREVIEW_TARGETED_ALERT", "CRITICAL": "URGENT_REVIEW"}[normalized_overall]
    data_quality = _data_quality(weather_source, historical_available, normalized_ml is not None, incident_catalog_available)
    assessment = {
        "overallRisk": normalized_overall,
        "mlRisk": normalized_ml,
        "confidence": confidence,
        "confidenceLabel": "AVAILABLE" if confidence is not None else "NOT_AVAILABLE",
        "dataQuality": data_quality,
        "factors": factors,
        "explanations": [factor["explanation"] for factor in factors],
        "recommendedAction": recommendation,
        "automaticAlert": False,
    }
    recent_incident = dict(incident) if incident else None
    if recent_incident:
        recent_incident["status"] = "VERIFIED · DEMO SCENARIO" if incident.get("verification_status") == "verified" else "SOURCE REVIEW REQUIRED · DEMO SCENARIO"
        recent_incident["classification"] = f"{normalize_risk(incident.get('demo_risk'), default='HIGH')} — DEMO CLASSIFICATION"
        recent_incident["location_precision"] = str(incident.get("location_precision") or "unknown").upper()

    return {
        "zone": {"zone_id": str(properties.get("zone_id") or ""), "name": str(properties.get("name") or properties.get("zone_id") or "Configured zone"), "configured_risk": configured_risk, "latitude": latitude, "longitude": longitude},
        "weather": weather or None,
        "weatherSource": weather_source,
        "environmentalValues": environmental_values,
        "historicalContext": {"nearby_count": int(historical_count or 0) if historical_available else None, "status": "AVAILABLE" if historical_available else "UNAVAILABLE", "classification": "HISTORICAL INVENTORY"},
        "recentIncident": recent_incident,
        "recentIncidentStatus": recent_incident["status"] if recent_incident else "NONE IDENTIFIED" if incident_catalog_available else "UNAVAILABLE",
        "mlRisk": {"risk": normalized_ml, "confidence": confidence, "status": "AVAILABLE" if normalized_ml else "UNAVAILABLE", "authority": "EXISTING ML PREDICTION"},
        "overallRisk": normalized_overall,
        "overallRiskBasis": "EXISTING ML + CONFIGURED ZONE LOGIC" if normalized_ml else "CONFIGURED ZONE RISK",
        "confidence": confidence,
        "confidenceLabel": assessment["confidenceLabel"],
        "factors": factors,
        "explanations": assessment["explanations"],
        "dataQuality": data_quality,
        "recommendedAction": recommendation,
        "automaticAlert": False,
        "assessment": assessment,
    }
