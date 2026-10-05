from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend_api
from database.connection import get_db
from database.models import AuditEvent


ZONE = {
    "type": "Feature",
    "properties": {"zone_id": "WYD-03", "name": "Wayanad Critical Scar", "risk_level": "HIGH"},
    "geometry": {"type": "Polygon", "coordinates": [[[76.06, 11.53], [76.18, 11.53], [76.18, 11.66], [76.06, 11.66], [76.06, 11.53]]]},
}


def member(user_id: str, *, inside: bool, phone: str = "+919876543210") -> dict:
    return {
        "_user_id": user_id, "_phone_number": phone, "inside": inside,
        "sms_eligible": True, "latitude": 11.58 if inside else 12.0,
        "longitude": 76.12 if inside else 77.0, "last_updated": "now", "current_risk": "HIGH",
    }


class OfflineDemoAlertTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        AuditEvent.__table__.create(engine)
        self.engine = engine
        self.Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        self.db = self.Session()
        self.simulation = SimpleNamespace(read_state=lambda: {"enabled": True})

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        backend_api.app.dependency_overrides.clear()

    def test_red_zone_calculation_handles_zero_and_multiple_users_with_safe_ids(self):
        with patch.object(backend_api, "_configured_zone_population", return_value=(ZONE, 3, [])):
            _feature, empty = backend_api._offline_demo_area("WYD-03", self.db)
        self.assertEqual(empty, [])

        private_members = [member("internal-one", inside=True), member("internal-two", inside=True), member("outside", inside=False)]
        with patch.object(backend_api, "_configured_zone_population", return_value=(ZONE, 3, private_members)):
            _feature, recipients = backend_api._offline_demo_area("WYD-03", self.db)
        self.assertEqual(len(recipients), 2)
        serialized = json.dumps(recipients)
        self.assertNotIn("internal-one", serialized)
        self.assertNotIn("+919876543210", serialized)
        self.assertNotIn("phone_number", serialized)
        self.assertTrue(all(item["displayId"].startswith("Citizen #") for item in recipients))

    def test_catalog_incident_radius_reuses_server_geofence_helper(self):
        incident = {"id": "incident-1", "title": "Catalog incident", "latitude": 11.55, "longitude": 76.13, "affected_radius_meters": 1000, "demo_risk": "CRITICAL"}
        rows = SimpleNamespace(all=lambda: [(SimpleNamespace(uid="private", phone_number="+919876543210"), SimpleNamespace(latitude=11.55, longitude=76.13))])
        db = SimpleNamespace(execute=lambda _statement: rows)
        geofence = Mock(return_value=[SimpleNamespace(zone_id="incident:incident-1")])
        with patch.object(backend_api, "load_incident_catalog", return_value=[incident]), patch.object(backend_api, "find_zone_matches", geofence):
            feature, recipients = backend_api._offline_demo_incident_area("incident-1", db)
        self.assertEqual(feature["properties"]["area_type"], "INCIDENT_RADIUS")
        self.assertEqual(len(feature["geometry"]["coordinates"][0]), 49)
        self.assertEqual(recipients[0]["status"], "INSIDE AFFECTED RADIUS")
        self.assertNotIn("private", json.dumps(recipients))
        geofence.assert_called_once()

    def test_send_is_explicit_simulation_and_never_calls_real_providers(self):
        recipients = [{"displayId": "Citizen #A1B2C3D4", "status": "INSIDE ZONE", "userType": "REAL_REGISTERED_USER", "smsRegistered": True, "bluetoothDemoEligible": True}]
        sms = Mock(side_effect=AssertionError("Twilio must not be called"))
        firebase = Mock(side_effect=AssertionError("Firebase must not be called"))
        alert_write = Mock(side_effect=AssertionError("real alert must not be written"))
        request = backend_api.OfflineDemoSendRequest(zone_id="WYD-03", channels=["SMS_DEMO", "BLUETOOTH_DEMO"], confirmed=True)
        with (
            patch.object(backend_api, "simulation_mode", self.simulation),
            patch.object(backend_api, "_offline_demo_area", return_value=(ZONE, recipients)),
            patch.object(backend_api, "send_sms_alert", sms),
            patch.object(backend_api, "create_alert", alert_write),
            patch("backend.auth.firebase_verify.verify_firebase_id_token", firebase),
        ):
            result = backend_api.send_offline_demo_alert(request, {"role": "Admin"}, self.db)

        sms.assert_not_called()
        firebase.assert_not_called()
        alert_write.assert_not_called()
        self.assertEqual(result["status"], "DEMO_DELIVERED")
        self.assertEqual({item["status"] for item in result["deliveries"]}, {"SIMULATED"})
        self.assertEqual({item["channel"] for item in result["deliveries"]}, {"SMS_DEMO", "BLUETOOTH_DEMO"})
        self.assertTrue(all(item["physical_delivery"] is False for item in result["deliveries"]))
        self.assertEqual(result["summary"], {"smsDemo": 1, "bluetoothDemo": 1, "realSms": 0, "realBluetooth": 0, "realAlerts": 0})
        event = self.db.scalar(select(AuditEvent))
        self.assertEqual(event.event_type, "OFFLINE_DEMO_ALERT_COMPLETED")
        self.assertEqual(event.mode, "SIMULATION")
        self.assertNotEqual(event.event_type, "ALERT_ACTIVATED")

    def test_confirmation_channels_risk_and_simulation_boundaries_are_enforced(self):
        with patch.object(backend_api, "simulation_mode", self.simulation), patch.object(backend_api, "_offline_demo_area", return_value=(ZONE, [])):
            with self.assertRaises(HTTPException) as unconfirmed:
                backend_api.send_offline_demo_alert(backend_api.OfflineDemoSendRequest(zone_id="WYD-03", channels=["SMS_DEMO"], confirmed=False), {}, self.db)
            with self.assertRaises(HTTPException) as invalid:
                backend_api.send_offline_demo_alert(backend_api.OfflineDemoSendRequest(zone_id="WYD-03", channels=["REAL_SMS"], confirmed=True), {}, self.db)
        self.assertEqual(unconfirmed.exception.status_code, 422)
        self.assertEqual(invalid.exception.status_code, 422)

        medium = {**ZONE, "properties": {**ZONE["properties"], "risk_level": "MEDIUM"}}
        with patch.object(backend_api, "_configured_zone_population", return_value=(medium, 0, [])), self.assertRaises(HTTPException) as risk_error:
            backend_api._offline_demo_area("WYD-03", self.db)
        self.assertEqual(risk_error.exception.status_code, 422)

        disabled = SimpleNamespace(read_state=lambda: {"enabled": False})
        with patch.object(backend_api, "simulation_mode", disabled), self.assertRaises(HTTPException) as mode_error:
            backend_api.preview_offline_demo_alert(backend_api.OfflineDemoAreaRequest(zone_id="WYD-03"), {}, self.db)
        self.assertEqual(mode_error.exception.status_code, 409)

    def test_http_endpoint_is_admin_only(self):
        backend_api.app.dependency_overrides[get_db] = lambda: self.db
        client = TestClient(backend_api.app, base_url="https://testserver")
        payload = {"zone_id": "WYD-03"}
        with (
            patch.object(backend_api, "simulation_mode", self.simulation),
            patch.object(backend_api, "_offline_demo_area", return_value=(ZONE, [])),
            patch("backend.auth.middleware.jwt_service.decode_token", return_value={"sub": "admin", "jti": "active", "role": "Admin"}),
            patch("backend.auth.middleware.is_user_session_active", return_value=True),
        ):
            admin = client.post("/admin/offline-demo-alerts/preview", headers={"Authorization": "Bearer admin"}, json=payload)
            missing = client.post("/admin/offline-demo-alerts/preview", json=payload)
        with (
            patch("backend.auth.middleware.jwt_service.decode_token", return_value={"sub": "citizen", "jti": "active", "role": "Citizen"}),
            patch("backend.auth.middleware.is_user_session_active", return_value=True),
        ):
            citizen = client.post("/admin/offline-demo-alerts/preview", headers={"Authorization": "Bearer citizen"}, json=payload)
        self.assertEqual(admin.status_code, 200)
        self.assertEqual(missing.status_code, 401)
        self.assertEqual(citizen.status_code, 403)

    def test_real_activation_still_returns_409_before_recipient_work(self):
        selection = Mock(side_effect=AssertionError("recipient work must remain blocked"))
        request = backend_api.AffectedZonePreviewRequest(zone_id="WYD-03", risk_level="HIGH", message="real", duration_minutes=60)
        with patch.object(backend_api, "simulation_mode", self.simulation), patch.object(backend_api, "_affected_zone_recipients", selection), self.assertRaises(HTTPException) as error:
            backend_api.activate_affected_zone_alert(request, {"role": "Admin"}, self.db)
        self.assertEqual(error.exception.status_code, 409)
        selection.assert_not_called()


if __name__ == "__main__":
    unittest.main()
