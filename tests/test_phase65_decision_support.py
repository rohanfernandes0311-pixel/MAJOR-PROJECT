from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import ANY, patch

import backend_api


ZONE = {
    "type": "Feature",
    "properties": {"zone_id": "WYD-03", "name": "Wayanad Critical Scar", "risk_level": "HIGH"},
    "geometry": {
        "type": "Polygon",
        "coordinates": [[[76.06, 11.53], [76.18, 11.53], [76.18, 11.66], [76.06, 11.66], [76.06, 11.53]]],
    },
}


class Phase65DecisionSupportTests(unittest.TestCase):
    def test_admin_intelligence_preserves_authoritative_decision_fields_without_notification(self) -> None:
        member = {
            "_user_id": "private-user", "_phone_number": "+919876543210", "inside": True,
            "sms_eligible": True, "latitude": 11.58, "longitude": 76.12,
            "last_updated": "2026-08-21T09:00:00Z", "current_risk": "HIGH",
        }
        weather = SimpleNamespace(fetch_weather_context=lambda *_: {
            "source_type": "real", "weather_severity": "high", "rainfall_mm": 120.0,
            "available_fields": ["rainfall_mm"],
        })
        with (
            patch.object(backend_api, "load_zones", return_value={"features": [ZONE]}),
            patch.object(backend_api, "weather_service", weather),
            patch.object(backend_api, "_historical_count_in_zone", return_value=5),
            patch.object(backend_api, "_latest_zone_ml_prediction", return_value=("HIGH", 0.82)),
            patch.object(backend_api, "load_incident_catalog", return_value=[]),
            patch.object(backend_api, "_configured_zone_population", return_value=(ZONE, 2, [member])),
            patch.object(backend_api, "send_sms_alert") as send_sms,
        ):
            result = backend_api.admin_zone_intelligence("WYD-03", {"role": "Admin"}, object())

        assessment = result["assessment"]
        self.assertEqual(assessment["overallRisk"], "HIGH")
        self.assertEqual(assessment["recommendedAction"], "PREVIEW_TARGETED_ALERT")
        self.assertEqual(assessment["confidence"], 0.82)
        self.assertEqual(assessment["dataQuality"], "GOOD")
        self.assertTrue(assessment["factors"])
        self.assertEqual(result["affected"]["insideUsers"], 1)
        self.assertEqual(result["affected"]["recipientCount"], 1)
        self.assertEqual(result["affected"]["smsEligibleCount"], 1)
        self.assertFalse(assessment["automaticAlert"])
        self.assertFalse(result["automaticAlert"])
        send_sms.assert_not_called()

    def test_existing_phase5_preview_remains_preview_only_and_authoritative(self) -> None:
        request = backend_api.AffectedZonePreviewRequest(
            zone_id="WYD-03", risk_level="HIGH", message="Review local conditions", duration_minutes=60,
        )
        recipient = {
            "user_id": "private-user", "phone_masked": "+91******3210", "sms_eligible": True,
            "latitude": 11.58, "longitude": 76.12, "last_updated": "now", "current_risk": "HIGH",
            "_sms_phone_number": "+919876543210",
        }
        with (
            patch.object(backend_api, "_affected_zone_recipients", return_value=("HIGH", "Review local conditions", ZONE, 2, [recipient])) as selection,
            patch.object(backend_api, "sms_configuration_status", return_value={"configured": False}),
            patch.object(backend_api, "simulation_mode", SimpleNamespace(read_state=lambda: {"enabled": False})),
            patch.object(backend_api, "send_sms_alert") as send_sms,
        ):
            result = backend_api.preview_affected_zone_recipients(request, {"role": "Admin"}, object())

        selection.assert_called_once_with(request, ANY)
        self.assertTrue(result["preview_only"])
        self.assertEqual(result["recipient_count"], 1)
        self.assertEqual(result["sms_eligible_count"], 1)
        send_sms.assert_not_called()


if __name__ == "__main__":
    unittest.main()
