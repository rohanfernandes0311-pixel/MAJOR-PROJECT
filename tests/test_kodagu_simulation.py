from __future__ import annotations

from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from openpyxl import load_workbook

import backend_api as api
from geofencing import find_zone_matches
from services.httpsms_export import HEADERS, build_workbook, generate_alert_message, select_sms_recipients
from services.simulation_mode_service import KODAGU_LOCATIONS, SimulationModeService


VERIFIED = {
    "type": "Feature",
    "properties": {"zone_id": "verified", "name": "Madikeri", "risk_level": "LOW", "verified": True},
    "geometry": {"type": "Polygon", "coordinates": [[[75.0, 12.0], [76.0, 12.0], [76.0, 13.0], [75.0, 13.0], [75.0, 12.0]]]},
}


class KodaguSimulationTests(unittest.TestCase):
    def setUp(self):
        self.service = SimulationModeService(Path(__file__).resolve().parents[1])
        self.service.record_event = Mock()

    def test_report_backed_location_allowlist_is_exact(self):
        self.assertEqual(KODAGU_LOCATIONS, (
            "Madikeri", "Virajpet", "Chittalli", "Perumbadi", "Makutta",
        ))
        self.assertNotIn("Mangalore", KODAGU_LOCATIONS)

    def test_high_and_critical_are_the_only_kodagu_levels(self):
        high = self.service.create_kodagu(location="Madikeri", risk="HIGH")
        self.assertEqual(high["effective_risk"], "HIGH")
        self.assertIn("LANDsense SIMULATION ALERT: High", high["alert_preview"]["message"])
        critical = self.service.create_kodagu(location="Virajpet", risk="CRITICAL")
        self.assertEqual(critical["effective_risk"], "CRITICAL")
        self.assertIn("risk simulated in Virajpet", critical["alert_preview"]["message"])
        for invalid in ("LOW", "MEDIUM", "EXTREME"):
            with self.assertRaises(ValueError):
                self.service.create_kodagu(location="Madikeri", risk=invalid)

    def test_no_geometry_is_invented(self):
        state = self.service.create_kodagu(location="Virajpet", risk="HIGH")
        self.assertIsNone(state["synthetic_zone"])
        self.assertEqual(state["geometry_status"], "unavailable_no_verified_geometry")
        self.assertEqual(state["route"]["status"], "unavailable")

    def test_verified_existing_geometry_is_copied_and_marked_synthetic(self):
        original = VERIFIED.copy()
        state = self.service.create_kodagu(location="Madikeri", risk="CRITICAL", verified_feature=VERIFIED)
        zone = state["synthetic_zone"]
        self.assertTrue(zone["properties"]["is_simulation"])
        self.assertTrue(zone["properties"]["synthetic"])
        self.assertEqual(zone["properties"]["risk_label"], "LandSense Simulation Risk Level")
        self.assertEqual(VERIFIED, original)

    def test_existing_geofence_includes_inside_and_excludes_outside(self):
        collection = {"type": "FeatureCollection", "features": [VERIFIED]}
        self.assertTrue(find_zone_matches(12.5, 75.5, collection))
        self.assertFalse(find_zone_matches(14.0, 75.5, collection))

    def test_recipient_dedupe_and_exact_excel_headers_without_send(self):
        members = [
            {"inside": True, "_alert_enabled": True, "_phone_number": "9876543210", "_user_id": "a"},
            {"inside": True, "_alert_enabled": True, "_phone_number": "+919876543210", "_user_id": "b"},
            {"inside": False, "_alert_enabled": True, "_phone_number": "+918888888888", "_user_id": "outside"},
        ]
        selected = select_sms_recipients(members)
        self.assertEqual(selected["affected_count"], 2)
        self.assertEqual(selected["sms_eligible_count"], 1)
        self.assertEqual(selected["duplicate_count"], 1)
        message = self.service.create_kodagu(location="Madikeri", risk="HIGH")["alert_preview"]["message"]
        content = build_workbook("+911111111111", selected["_phones"], message)
        workbook = load_workbook(BytesIO(content))
        self.addCleanup(workbook.close)
        self.assertEqual(tuple(cell.value for cell in workbook.active[1]), HEADERS)
        self.assertIn("SIMULATION ALERT", workbook.active["C2"].value)

    def test_trigger_is_preview_only_and_reset_clears_all_simulation_state(self):
        self.service.create_kodagu(location="Madikeri", risk="CRITICAL", verified_feature=VERIFIED)
        self.service.set_kodagu_results(recipients=[
            {"display_id": "Citizen #ELIGIBLE", "sms_eligible": True},
            {"display_id": "Citizen #DISABLED", "sms_eligible": False},
        ], sms_eligible_users=1, route=None)
        triggered = self.service.trigger_kodagu(["Citizen #ELIGIBLE", "Citizen #DISABLED", "Citizen #OUTSIDE"])
        self.assertTrue(triggered["triggered"])
        self.assertTrue(triggered["external_notifications_suppressed"])
        self.assertEqual(triggered["selected_recipient_ids"], ["Citizen #ELIGIBLE"])
        self.assertEqual(triggered["alert_preview"]["recipients"], 1)
        reset = self.service.set_state(enabled=False, forced_risk="LOW", escalation_enabled=False, scenario_name="Normal", zones_geo=None)
        self.assertFalse(reset["enabled"])
        self.assertIsNone(reset["synthetic_zone"])
        self.assertEqual(reset["recipients"], [])
        self.assertIsNone(reset["alert_preview"])
        self.assertIsNone(reset["route"])

    def test_kodagu_routes_are_admin_only(self):
        api.app.dependency_overrides[api.get_db] = lambda: object()
        self.addCleanup(api.app.dependency_overrides.clear)
        self.addCleanup(lambda: api.simulation_mode.set_state(enabled=False, forced_risk="LOW", escalation_enabled=False, scenario_name="Normal", zones_geo=None))
        with patch.object(api, "load_zones", return_value={"type": "FeatureCollection", "features": []}), patch.object(api.simulation_mode, "record_event"), TestClient(api.app, base_url="https://testserver") as client:
            self.assertEqual(client.get("/admin/simulation/kodagu/locations").status_code, 401)
            with patch("backend.auth.middleware.jwt_service.decode_token", return_value={"sub": "test", "jti": "active", "role": "Citizen"}), patch("backend.auth.middleware.is_user_session_active", return_value=True):
                self.assertEqual(client.get("/admin/simulation/kodagu/locations", headers={"Authorization": "Bearer test"}).status_code, 403)
                self.assertEqual(client.post("/admin/simulation/kodagu/create", headers={"Authorization": "Bearer test"}, json={"location": "Virajpet", "risk_level": "HIGH"}).status_code, 403)
            with patch("backend.auth.middleware.jwt_service.decode_token", return_value={"sub": "admin", "jti": "active", "role": "Admin"}), patch("backend.auth.middleware.is_user_session_active", return_value=True):
                response = client.get("/admin/simulation/kodagu/locations", headers={"Authorization": "Bearer test"})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["risk_levels"], ["HIGH", "CRITICAL"])
                created = client.post("/admin/simulation/kodagu/create", headers={"Authorization": "Bearer test"}, json={"location": "Virajpet", "risk_level": "HIGH"})
                self.assertEqual(created.status_code, 200)
                self.assertTrue(created.json()["state"]["enabled"])
                self.assertEqual(created.json()["state"]["location"], "Virajpet")


if __name__ == "__main__":
    unittest.main()
