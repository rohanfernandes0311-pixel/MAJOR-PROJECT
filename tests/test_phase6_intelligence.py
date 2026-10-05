from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import backend_api
from fastapi import HTTPException
from fastapi.testclient import TestClient
from services.phase6_intelligence import build_zone_intelligence, find_incident_for_zone, load_incident_catalog


ZONE = {
    "type": "Feature",
    "properties": {"zone_id": "WYD-03", "name": "Wayanad Critical Scar", "risk_level": "HIGH"},
    "geometry": {
        "type": "Polygon",
        "coordinates": [[[76.06, 11.53], [76.18, 11.53], [76.18, 11.66], [76.06, 11.66], [76.06, 11.53]]],
    },
}


class Phase6IntelligenceTests(unittest.TestCase):
    def _build(self, risk="HIGH", **overrides):
        zone = {**ZONE, "properties": {**ZONE["properties"], "risk_level": risk}}
        values = {
            "weather": {"source_type": "real", "weather_severity": "low", "rainfall_mm": 2.0, "available_fields": ["rainfall_mm"]},
            "historical_count": 0,
            "historical_available": True,
            "ml_risk": risk,
            "overall_risk": risk,
            "incident": None,
            "incident_catalog_available": True,
        }
        values.update(overrides)
        return build_zone_intelligence(zone, **values)

    def test_supported_risks_have_deterministic_recommendations(self) -> None:
        expected = {
            "SAFE": "MONITOR", "LOW": "MONITOR", "MEDIUM": "PREPARE_WARNING",
            "HIGH": "PREVIEW_TARGETED_ALERT", "CRITICAL": "URGENT_REVIEW",
        }
        for risk, recommendation in expected.items():
            with self.subTest(risk=risk):
                assessment = self._build(risk)["assessment"]
                self.assertEqual(assessment["overallRisk"], risk)
                self.assertEqual(assessment["recommendedAction"], recommendation)
                self.assertFalse(assessment["automaticAlert"])

    def test_invalid_configured_risk_is_rejected(self) -> None:
        invalid_zone = {**ZONE, "properties": {**ZONE["properties"], "risk_level": "SEVERE"}}
        with self.assertRaisesRegex(ValueError, "Configured zone risk is invalid"):
            build_zone_intelligence(
                invalid_zone, weather=None, historical_count=None, historical_available=False,
                ml_risk=None, incident_catalog_available=False,
            )

    def test_real_weather_historical_context_and_existing_ml_are_consumed(self) -> None:
        result = build_zone_intelligence(
            ZONE,
            weather={
                "source_type": "real", "provider": "test", "weather_severity": "high",
                "rainfall_mm": 124.0, "temperature_c": 27.0, "humidity_pct": 88.0,
                "wind_speed_mps": 4.0,
                "available_fields": ["rainfall_mm", "temperature_c", "humidity_pct", "wind_speed_mps"],
            },
            historical_count=142,
            historical_available=True,
            ml_risk="HIGH",
            ml_confidence=0.91,
            overall_risk="HIGH",
        )

        self.assertEqual(result["weatherSource"], "REAL")
        self.assertEqual(result["environmentalValues"]["rainfall"]["status"], "REAL")
        self.assertEqual(result["historicalContext"]["nearby_count"], 142)
        self.assertEqual(result["historicalContext"]["classification"], "HISTORICAL INVENTORY")
        self.assertEqual(result["mlRisk"]["risk"], "HIGH")
        self.assertEqual(result["overallRiskBasis"], "EXISTING ML + CONFIGURED ZONE LOGIC")
        self.assertEqual(result["assessment"]["confidenceLabel"], "AVAILABLE")
        self.assertEqual(result["assessment"]["dataQuality"], "GOOD")
        self.assertTrue(result["assessment"]["factors"])
        self.assertTrue(result["assessment"]["explanations"])
        self.assertFalse(result["automaticAlert"])

    def test_simulated_rain_does_not_make_other_weather_fields_simulated(self) -> None:
        result = build_zone_intelligence(
            ZONE,
            weather={"source_type": "simulated", "rainfall_mm": 22.0, "available_fields": ["rainfall_mm"]},
            historical_count=None,
            historical_available=False,
            ml_risk=None,
        )

        self.assertEqual(result["environmentalValues"]["rainfall"]["status"], "SIMULATED")
        self.assertEqual(result["environmentalValues"]["temperature"]["status"], "UNAVAILABLE")
        self.assertEqual(result["historicalContext"]["status"], "UNAVAILABLE")
        self.assertEqual(result["mlRisk"]["status"], "UNAVAILABLE")
        self.assertEqual(result["overallRisk"], "HIGH")
        self.assertEqual(result["overallRiskBasis"], "CONFIGURED ZONE RISK")
        self.assertEqual(result["assessment"]["confidenceLabel"], "NOT_AVAILABLE")
        self.assertEqual(result["assessment"]["dataQuality"], "LIMITED")

    def test_verified_and_demo_incidents_preserve_provenance(self) -> None:
        verified = {"id": "v", "title": "Verified", "date": "2026-07-07", "latitude": 11.55, "longitude": 76.13, "location_precision": "approximate", "demo_risk": "CRITICAL", "verification_status": "verified"}
        demo = {**verified, "id": "d", "verification_status": "source_review_required"}

        verified_result = self._build(incident=verified)
        demo_result = self._build(incident=demo)

        self.assertEqual(verified_result["recentIncident"]["status"], "VERIFIED · DEMO SCENARIO")
        self.assertEqual(demo_result["recentIncident"]["status"], "SOURCE REVIEW REQUIRED · DEMO SCENARIO")
        verified_factor = next(item for item in verified_result["factors"] if item["factor"] == "recent_incident")
        demo_factor = next(item for item in demo_result["factors"] if item["factor"] == "recent_incident")
        self.assertEqual(verified_factor["impact"], "ELEVATED")
        self.assertEqual(demo_factor["status"], "DEMO_SCENARIO")
        self.assertIn("not an official live risk classification", demo_factor["explanation"])

    def test_missing_incident_and_missing_sources_are_explicit(self) -> None:
        no_incident = self._build(incident=None)
        unavailable = self._build(
            weather=None, historical_count=None, historical_available=False, ml_risk=None,
            incident=None, incident_catalog_available=False,
        )

        incident_factor = next(item for item in no_incident["factors"] if item["factor"] == "recent_incident")
        self.assertEqual(incident_factor["status"], "NONE_IDENTIFIED")
        self.assertIn("not evidence of safety", incident_factor["explanation"])
        self.assertEqual(unavailable["assessment"]["dataQuality"], "UNAVAILABLE")
        self.assertEqual(unavailable["assessment"]["confidenceLabel"], "NOT_AVAILABLE")

    def test_shared_catalog_matches_the_verified_wayanad_incident(self) -> None:
        incidents = load_incident_catalog(backend_api.INCIDENT_CATALOG_PATH)
        incident = find_incident_for_zone(ZONE, incidents)

        self.assertEqual(incident["id"], "wayanad-kalladi-2026-07-07")
        self.assertEqual(incident["location_precision"], "approximate")

    def test_admin_endpoint_survives_missing_weather_and_historical_inventory(self) -> None:
        unavailable_weather = SimpleNamespace(fetch_weather_context=lambda *_: (_ for _ in ()).throw(RuntimeError("offline")))
        with (
            patch.object(backend_api, "load_zones", return_value={"features": [ZONE]}),
            patch.object(backend_api, "weather_service", unavailable_weather),
            patch.object(backend_api, "_historical_count_in_zone", side_effect=AttributeError("inventory unavailable")),
            patch.object(backend_api, "_latest_zone_ml_prediction", return_value=(None, None)),
        ):
            result = backend_api.admin_zone_intelligence("WYD-03", {"role": "Admin"}, object())

        self.assertEqual(result["weatherSource"], "UNAVAILABLE")
        self.assertEqual(result["historicalContext"]["status"], "UNAVAILABLE")
        self.assertEqual(result["mlRisk"]["status"], "UNAVAILABLE")
        self.assertEqual(result["assessment"]["confidenceLabel"], "NOT_AVAILABLE")
        self.assertFalse(result["automaticAlert"])

    def test_invalid_zone_is_rejected(self) -> None:
        with patch.object(backend_api, "load_zones", return_value={"features": [ZONE]}):
            with self.assertRaises(HTTPException) as raised:
                backend_api.admin_zone_intelligence("UNKNOWN", {"role": "Admin"}, object())
        self.assertEqual(raised.exception.status_code, 404)

    def test_unauthorized_admin_request_is_rejected(self) -> None:
        with TestClient(backend_api.app, base_url="https://testserver") as client:
            response = client.get("/admin/intelligence/zones/WYD-03")
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
