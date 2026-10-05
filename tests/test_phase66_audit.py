from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend_api
from database.connection import get_db
from database.models import Alert, AuditEvent
from services.audit_service import public_audit_event, record_audit_event


ZONE = {
    "type": "Feature",
    "properties": {"zone_id": "WYD-03", "name": "Wayanad Critical Scar", "risk_level": "HIGH"},
    "geometry": {"type": "Polygon", "coordinates": [[[76.06, 11.53], [76.18, 11.53], [76.18, 11.66], [76.06, 11.66], [76.06, 11.53]]]},
}


class _Simulation:
    def __init__(self, enabled=False):
        self.enabled = enabled
        self.state = {"enabled": enabled, "effective_risk": "HIGH", "forced_risk": "HIGH", "scenario_name": "High Risk", "danger_zone_id": "WYD-03", "danger_zone_name": "Wayanad Critical Scar"}

    def read_state(self):
        return dict(self.state)

    def set_state(self, *, enabled, forced_risk, escalation_enabled, scenario_name, zones_geo):
        self.enabled = enabled
        self.state = {
            "enabled": enabled, "effective_risk": forced_risk if enabled else "LOW", "forced_risk": forced_risk,
            "scenario_name": scenario_name, "danger_zone_id": "WYD-03" if enabled else None,
            "danger_zone_name": "Wayanad Critical Scar" if enabled else None,
        }
        return dict(self.state)


class Phase66AuditTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        AuditEvent.__table__.create(self.engine)
        Alert.__table__.create(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.db = self.Session()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        backend_api.app.dependency_overrides.clear()

    def _events(self):
        return self.db.scalars(select(AuditEvent).order_by(AuditEvent.id.asc())).all()

    def test_events_are_persistent_newest_first_paginated_and_snapshotted(self):
        first = record_audit_event(
            self.db, event_type="INTELLIGENCE_CALCULATED", mode="REAL", zone_id="WYD-03",
            zone_name="Wayanad Critical Scar", risk="HIGH", message="Assessment calculated.",
            metadata={"confidence": 0.82, "dataQuality": "GOOD", "recommendedAction": "PREVIEW_TARGETED_ALERT", "automaticAlert": False},
        )
        snapshot = public_audit_event(first)
        record_audit_event(self.db, event_type="RECIPIENT_PREVIEW_OPENED", mode="REAL", zone_id="WYD-03", message="Preview opened.", metadata={"recipientCount": 4})
        record_audit_event(self.db, event_type="ALERT_ACTIVATED", mode="REAL", zone_id="WYD-03", message="Activated.", metadata={"recipientCount": 4})

        page = backend_api.admin_audit_events(limit=2, offset=0, category=None, mode=None, _={"role": "Admin"}, db=self.db)
        second_page = backend_api.admin_audit_events(limit=2, offset=2, category=None, mode=None, _={"role": "Admin"}, db=self.db)
        self.assertEqual([item["eventType"] for item in page["events"]], ["ALERT_ACTIVATED", "RECIPIENT_PREVIEW_OPENED"])
        self.assertTrue(page["hasMore"])
        self.assertEqual(second_page["events"][0]["eventType"], "INTELLIGENCE_CALCULATED")
        self.assertEqual(snapshot["metadata"]["confidence"], 0.82)
        self.assertEqual(snapshot["metadata"]["recommendedAction"], "PREVIEW_TARGETED_ALERT")
        self.assertFalse(snapshot["metadata"]["automaticAlert"])
        self.assertRegex(snapshot["eventId"], r"^AUD-\d{8}$")
        self.assertNotIn("id", snapshot)

    def test_audit_endpoint_requires_admin_and_validates_bounds(self):
        backend_api.app.dependency_overrides[get_db] = lambda: self.db
        client = TestClient(backend_api.app, base_url="https://testserver")
        missing = client.get("/admin/audit/events")
        with (
            patch("backend.auth.middleware.jwt_service.decode_token", return_value={"sub": "citizen", "jti": "active", "role": "Citizen"}),
            patch("backend.auth.middleware.is_user_session_active", return_value=True),
        ):
            citizen = client.get("/admin/audit/events", headers={"Authorization": "Bearer citizen"})
        with (
            patch("backend.auth.middleware.jwt_service.decode_token", return_value={"sub": "admin", "jti": "active", "role": "Admin"}),
            patch("backend.auth.middleware.is_user_session_active", return_value=True),
        ):
            admin = client.get("/admin/audit/events?limit=10", headers={"Authorization": "Bearer admin"})
            invalid = client.get("/admin/audit/events?limit=0", headers={"Authorization": "Bearer admin"})
        self.assertEqual(missing.status_code, 401)
        self.assertEqual(citizen.status_code, 403)
        self.assertEqual(admin.status_code, 200)
        self.assertEqual(invalid.status_code, 422)

    def test_zone_and_demo_ui_events_are_controlled_deduplicated_and_mode_safe(self):
        with patch.object(backend_api, "load_zones", return_value={"features": [ZONE]}):
            request = backend_api.AdminAuditUiEventRequest(event_type="ZONE_SELECTED", zone_id="WYD-03")
            first = backend_api.record_admin_ui_audit_event(request, {"role": "Admin"}, self.db)
            duplicate = backend_api.record_admin_ui_audit_event(request, {"role": "Admin"}, self.db)
        self.assertEqual(first["event"]["eventId"], duplicate["event"]["eventId"])

        selected = backend_api.AdminAuditUiEventRequest(event_type="INCIDENT_SELECTED", incident_id="wayanad-kalladi-2026-07-07")
        selected_result = backend_api.record_admin_ui_audit_event(selected, {"role": "Admin"}, self.db)
        self.assertEqual(selected_result["event"]["mode"], "DEMO")
        with patch.object(backend_api, "simulation_mode", _Simulation(enabled=True)):
            launched = backend_api.record_admin_ui_audit_event(
                backend_api.AdminAuditUiEventRequest(event_type="DEMO_INCIDENT_LAUNCHED", incident_id="wayanad-kalladi-2026-07-07", simulated_count=9),
                {"role": "Admin"}, self.db,
            )
            generated = backend_api.record_admin_ui_audit_event(
                backend_api.AdminAuditUiEventRequest(event_type="DEMO_ALERT_GENERATED", incident_id="wayanad-kalladi-2026-07-07", simulated_count=9),
                {"role": "Admin"}, self.db,
            )
        self.assertEqual(launched["event"]["mode"], "SIMULATION")
        self.assertEqual(generated["event"]["metadata"]["simulatedParticipants"], 9)
        self.assertTrue(generated["event"]["metadata"]["externalNotificationsSuppressed"])
        with self.assertRaises(HTTPException):
            backend_api.record_admin_ui_audit_event(
                backend_api.AdminAuditUiEventRequest(event_type="ALERT_ACTIVATED", zone_id="WYD-03"),
                {"role": "Admin"}, self.db,
            )

    def test_intelligence_and_affected_population_create_historical_safe_events(self):
        member = {"_user_id": "secret", "_phone_number": "+919876543210", "inside": True, "sms_eligible": True, "latitude": 11.58, "longitude": 76.12, "last_updated": "truthful-time", "current_risk": "HIGH"}
        weather = SimpleNamespace(fetch_weather_context=lambda *_: {"source_type": "real", "weather_severity": "high", "rainfall_mm": 120.0, "available_fields": ["rainfall_mm"]})
        with (
            patch.object(backend_api, "load_zones", return_value={"features": [ZONE]}),
            patch.object(backend_api, "weather_service", weather),
            patch.object(backend_api, "_historical_count_in_zone", return_value=4),
            patch.object(backend_api, "_latest_zone_ml_prediction", return_value=("HIGH", 0.82)),
            patch.object(backend_api, "load_incident_catalog", return_value=[]),
            patch.object(backend_api, "_configured_zone_population", return_value=(ZONE, 2, [member])),
        ):
            result = backend_api.admin_zone_intelligence("WYD-03", {"role": "Admin"}, self.db)
        events = self._events()
        self.assertEqual([event.event_type for event in events], ["INTELLIGENCE_CALCULATED", "AFFECTED_POPULATION_CALCULATED"])
        snapshot = json.loads(events[0].metadata_json)
        self.assertEqual(snapshot["confidence"], 0.82)
        self.assertEqual(snapshot["dataQuality"], "GOOD")
        self.assertEqual(snapshot["recommendedAction"], "PREVIEW_TARGETED_ALERT")
        self.assertFalse(snapshot["automaticAlert"])
        population = json.loads(events[1].metadata_json)
        self.assertEqual(population["realUsersInside"], 1)
        self.assertEqual(population["eligibleRecipients"], 1)
        result["assessment"]["recommendedAction"] = "MUTATED_CURRENT_VALUE"
        self.assertEqual(json.loads(events[0].metadata_json)["recommendedAction"], "PREVIEW_TARGETED_ALERT")

    def test_preview_and_activation_events_are_distinct_and_authoritative(self):
        recipient = {"user_id": "private", "phone_masked": "+91******3210", "sms_eligible": True, "_sms_phone_number": "+919876543210", "latitude": 11.58, "longitude": 76.12, "last_updated": "now", "current_risk": "HIGH"}
        request = backend_api.AffectedZonePreviewRequest(zone_id="WYD-03", risk_level="HIGH", message="Review conditions", duration_minutes=60, send_sms=False)
        with (
            patch.object(backend_api, "_affected_zone_recipients", return_value=("HIGH", "Review conditions", ZONE, 2, [recipient])),
            patch.object(backend_api, "sms_configuration_status", return_value={"configured": False, "provider": "twilio"}),
            patch.object(backend_api, "simulation_mode", _Simulation(enabled=False)),
        ):
            preview = backend_api.preview_affected_zone_recipients(request, {"role": "Admin"}, self.db)
            activation = backend_api.activate_affected_zone_alert(request, {"role": "Admin"}, self.db)
        self.assertTrue(preview["preview_only"])
        self.assertEqual(activation["in_app_created_count"], 1)
        self.assertEqual([event.event_type for event in self._events()], ["RECIPIENT_PREVIEW_OPENED", "ALERT_ACTIVATED"])
        self.assertNotIn("ALERT_ACTIVATED", self._events()[0].message)

    def test_failed_activation_is_recorded_but_simulation_guard_writes_nothing(self):
        request = backend_api.AffectedZonePreviewRequest(zone_id="WYD-03", risk_level="HIGH", message="Review", duration_minutes=60)
        with (
            patch.object(backend_api, "simulation_mode", _Simulation(enabled=False)),
            patch.object(backend_api, "_affected_zone_recipients", side_effect=HTTPException(status_code=404, detail="Configured zone unavailable")),
            patch.object(backend_api, "load_zones", return_value={"features": [ZONE]}),
            self.assertRaises(HTTPException),
        ):
            backend_api.activate_affected_zone_alert(request, {"role": "Admin"}, self.db)
        self.assertEqual(self._events()[-1].event_type, "ALERT_ACTIVATION_FAILED")
        before = len(self._events())
        with patch.object(backend_api, "simulation_mode", _Simulation(enabled=True)), self.assertRaises(HTTPException) as raised:
            backend_api.activate_affected_zone_alert(request, {"role": "Admin"}, self.db)
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(len(self._events()), before)

    def test_simulation_start_stop_are_backend_events(self):
        simulation = _Simulation(enabled=False)
        with patch.object(backend_api, "simulation_mode", simulation), patch.object(backend_api, "load_zones", return_value={"features": [ZONE]}):
            backend_api.admin_simulation_toggle(backend_api.SimulationToggleRequest(enabled=True, forced_risk="HIGH", scenario_name="High Risk"), {"role": "Admin"}, self.db)
            backend_api.admin_simulation_toggle(backend_api.SimulationToggleRequest(enabled=False, forced_risk="LOW", scenario_name="Normal"), {"role": "Admin"}, self.db)
        self.assertEqual([event.event_type for event in self._events()], ["SIMULATION_STARTED", "SIMULATION_STOPPED"])
        self.assertTrue(all(event.mode == "SIMULATION" for event in self._events()))

    def test_sensitive_and_raw_location_metadata_is_never_persisted_or_returned(self):
        event = record_audit_event(
            self.db, event_type="ZONE_SELECTED", mode="REAL", zone_id="WYD-03", message="Selected.",
            metadata={"phone": "+919876543210", "otp": "123456", "token": "secret", "latitude": 11.5, "longitude": 76.1, "recommendedAction": "MONITOR"},
        )
        serialized = json.dumps(public_audit_event(event))
        for forbidden in ("+919876543210", "123456", "secret", "latitude", "longitude", "phone", "otp", "token"):
            self.assertNotIn(forbidden, serialized.lower())
        self.assertIn("MONITOR", serialized)


if __name__ == "__main__":
    unittest.main()
