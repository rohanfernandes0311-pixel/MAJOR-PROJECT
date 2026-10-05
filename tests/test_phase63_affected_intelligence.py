from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

import backend_api


ZONE = {
    "type": "Feature",
    "properties": {"zone_id": "RGD-01", "name": "Raigad High Risk Belt", "risk_level": "HIGH"},
    "geometry": {"type": "Polygon", "coordinates": [[[73.22, 18.34], [73.35, 18.34], [73.35, 18.47], [73.22, 18.47], [73.22, 18.34]]]},
}


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class _PopulationDb:
    def __init__(self, rows, scalar_values):
        self.rows = rows
        self.scalar_values = iter(scalar_values)

    def execute(self, _statement):
        return _Rows(self.rows)

    def scalar(self, _statement):
        return next(self.scalar_values, None)


def _user(uid, phone="+919876543210", enabled=True):
    return SimpleNamespace(uid=uid, phone_number=phone, alert_enabled=1 if enabled else 0)


def _location(latitude, longitude):
    return SimpleNamespace(latitude=latitude, longitude=longitude, last_updated="2026-08-21T09:00:00Z")


class Phase63AffectedIntelligenceTests(unittest.TestCase):
    def test_authoritative_population_calculates_inside_outside_and_eligibility(self) -> None:
        rows = [
            (_user("inside-eligible"), _location(18.40, 73.29)),
            (_user("inside-opted-out", enabled=False), _location(18.42, 73.27)),
            (_user("outside"), _location(19.0, 74.0)),
        ]
        with patch.object(backend_api, "load_zones", return_value={"features": [ZONE]}):
            feature, total_registered, members = backend_api._configured_zone_population("RGD-01", _PopulationDb(rows, [5, "HIGH", "MEDIUM"]))

        self.assertEqual(feature["properties"]["zone_id"], "RGD-01")
        self.assertEqual(total_registered, 5)
        self.assertEqual(sum(item["inside"] for item in members), 2)
        self.assertEqual(sum(not item["inside"] for item in members), 1)
        self.assertEqual(sum(item["inside"] and item["sms_eligible"] for item in members), 1)

    def test_intelligence_affected_population_is_sanitized_and_alert_safe(self) -> None:
        members = [
            {"_user_id": "private-real-id", "_phone_number": "+919876543210", "inside": True, "sms_eligible": True, "latitude": 18.4, "longitude": 73.29, "last_updated": "now", "current_risk": "HIGH"},
            {"_user_id": "outside-id", "_phone_number": "+919999999999", "inside": False, "sms_eligible": True, "latitude": 19.0, "longitude": 74.0, "last_updated": "now", "current_risk": None},
        ]
        weather = SimpleNamespace(fetch_weather_context=lambda *_: None)
        with (
            patch.object(backend_api, "load_zones", return_value={"features": [ZONE]}),
            patch.object(backend_api, "weather_service", weather),
            patch.object(backend_api, "_historical_count_in_zone", return_value=0),
            patch.object(backend_api, "_latest_zone_ml_prediction", return_value=("HIGH", None)),
            patch.object(backend_api, "load_incident_catalog", return_value=[]),
            patch.object(backend_api, "_configured_zone_population", return_value=(ZONE, 4, members)),
        ):
            result = backend_api.admin_zone_intelligence("RGD-01", {"role": "Admin"}, object())

        affected = result["affected"]
        self.assertEqual(affected["insideUsers"], 1)
        self.assertEqual(affected["outsideUsers"], 1)
        self.assertEqual(affected["recipientCount"], 1)
        self.assertEqual(affected["smsEligibleCount"], 1)
        self.assertEqual(affected["simulatedUsers"], 0)
        self.assertFalse(affected["automaticAlert"])
        self.assertFalse(result["automaticAlert"])
        for user in affected["users"]:
            self.assertEqual(set(user), {"displayId", "status", "inside", "recipientEligible", "smsEligible", "latitude", "longitude", "lastUpdated", "currentRisk"})
            self.assertTrue(user["displayId"].startswith("Citizen #"))
            self.assertNotIn("private-real-id", str(user))
            self.assertNotIn("+91", str(user))

    def test_zero_located_users_is_a_valid_available_population(self) -> None:
        with patch.object(backend_api, "load_zones", return_value={"features": [ZONE]}):
            _feature, total_registered, members = backend_api._configured_zone_population("RGD-01", _PopulationDb([], [3]))
        self.assertEqual(total_registered, 3)
        self.assertEqual(members, [])

    def test_phase5_preview_and_population_use_the_same_inside_members(self) -> None:
        rows = [
            (_user("inside"), _location(18.40, 73.29)),
            (_user("outside"), _location(19.0, 74.0)),
        ]
        request = backend_api.AffectedZonePreviewRequest(zone_id="RGD-01", risk_level="HIGH", message="Preview", duration_minutes=60)
        with (
            patch.object(backend_api, "load_zones", return_value={"features": [ZONE]}),
            patch.object(backend_api, "sms_configuration_status", return_value={"configured": False}),
            patch.object(backend_api, "simulation_mode", SimpleNamespace(read_state=lambda: {"enabled": False})),
        ):
            _feature, _total, members = backend_api._configured_zone_population("RGD-01", _PopulationDb(rows, [2, "HIGH"]))
            preview = backend_api.preview_affected_zone_recipients(request, {"role": "Admin"}, _PopulationDb(rows, [2, "HIGH"]))
        self.assertEqual(preview["recipient_count"], sum(member["inside"] for member in members))

    def test_invalid_and_unauthorized_requests_are_rejected(self) -> None:
        with patch.object(backend_api, "load_zones", return_value={"features": [ZONE]}):
            with self.assertRaises(HTTPException) as raised:
                backend_api.admin_zone_intelligence("UNKNOWN", {"role": "Admin"}, object())
        self.assertEqual(raised.exception.status_code, 404)

        with TestClient(backend_api.app, base_url="https://testserver") as client:
            response = client.get("/admin/intelligence/zones/RGD-01")
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
