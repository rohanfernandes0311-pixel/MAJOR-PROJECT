"""Export integration tests use isolated SQLite fixtures, never the runtime DB."""
from io import BytesIO
from urllib.parse import quote
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend_api as api
from database.models import User, Location, LocationEvent
from services.httpsms_export import HEADERS, generate_alert_message, normalize_phone

ZONE = {"type": "Feature", "properties": {"zone_id": "demo", "name": "Madikeri", "risk_level": "CRITICAL"},
        "geometry": {"type": "Polygon", "coordinates": [[[75, 12], [76, 12], [76, 13], [75, 13], [75, 12]]]}}


class HttpSmsExportTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        for model in (User, Location, LocationEvent):
            model.__table__.create(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)
        for patcher in (
            patch.object(api, "load_zones", return_value={"type": "FeatureCollection", "features": [ZONE]}),
            patch.object(api, "simulation_mode", SimpleNamespace(read_state=lambda: {"enabled": True})),
            patch.dict("os.environ", {"HTTPSMS_FROM_NUMBER": "18005550199"}),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def add_user(self, uid, phone, enabled=1, lat=12.5, lon=75.5):
        self.db.add(User(uid=uid, phone_number=phone, phone_hash=uid, name=uid,
                         created_at="2020-01-01", last_login="2020-01-01", alert_enabled=enabled,
                         last_device_hash="fixture", role="Citizen"))
        self.db.add(Location(user_id=uid, latitude=lat, longitude=lon, last_updated="2020-01-01"))
        self.db.commit()

    def selected_ids(self):
        preview = api.preview_httpsms_excel("demo", {}, self.db)
        return ",".join(item["display_id"] for item in preview["recipients"] if item["sms_eligible"])

    def preview(self):
        return api.preview_httpsms_excel("demo", {}, self.db, recipient_ids=self.selected_ids())

    def download(self, **kwargs):
        return api.download_httpsms_excel("demo", {}, self.db, recipient_ids=self.selected_ids(), **kwargs)

    def test_workbook_only_contains_inside_opted_in_unique_valid_numbers(self):
        self.add_user("inside", "9148682207")
        self.add_user("outside", "+917795530769", lat=14)
        self.add_user("disabled", "+918888888888", enabled=0)
        self.add_user("duplicate", " +91 9148682207 ")
        self.add_user("invalid", "bad-phone")
        preview = self.preview()
        self.assertEqual(preview["affected_count"], 4)
        self.assertEqual(preview["sms_eligible_count"], 1)
        self.assertEqual(preview["duplicate_count"], 1)
        self.assertEqual(len(preview["invalid_recipients"]), 0)
        self.assertNotIn("_phones", preview)
        with patch.object(api, "send_sms_alert") as sms, patch.object(api, "create_alert") as alert:
            response = self.download(revision=preview["revision"])
        sms.assert_not_called()
        alert.assert_not_called()
        workbook = load_workbook(BytesIO(response.body))
        self.addCleanup(workbook.close)
        rows = list(workbook.active.values)
        self.assertEqual(rows[0], HEADERS)
        self.assertEqual(len(rows) - 1, preview["sms_eligible_count"])
        self.assertEqual(rows[1], ("18005550199", "+919148682207", generate_alert_message("CRITICAL", "Madikeri"), None))
        self.assertEqual(workbook.active["B2"].data_type, "s")
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_high_message(self):
        self.assertEqual(generate_alert_message("HIGH", "Madikeri"), "LANDsense ALERT: High landslide risk detected near Madikeri. Please stay alert, avoid unstable slopes, and follow the recommended safer route.")

    def test_omitted_selection_exports_nobody_and_preview_keeps_eligible_list(self):
        self.add_user("one", "9148682207")
        self.add_user("two", "7795530769")
        preview = api.preview_httpsms_excel("demo", {}, self.db)
        self.assertEqual(preview["eligible_count"], 2)
        self.assertEqual(preview["selected_count"], 0)
        self.assertFalse(preview["download_enabled"])
        with self.assertRaises(HTTPException):
            api.download_httpsms_excel("demo", {}, self.db)
        selected = api._safe_citizen_id("one")
        preview = api.preview_httpsms_excel("demo", {}, self.db, recipient_ids=selected)
        self.assertEqual(len(preview["recipients"]), 2)
        self.assertEqual(preview["selected_count"], 1)
        response = api.download_httpsms_excel("demo", {}, self.db, recipient_ids=selected, revision=preview["revision"])
        workbook = load_workbook(BytesIO(response.body))
        self.addCleanup(workbook.close)
        self.assertEqual([row[1] for row in list(workbook.active.values)[1:]], ["+919148682207"])

    def test_outside_selection_rejected_by_server(self):
        self.add_user("outside", "7795530769", lat=14)
        with self.assertRaises(HTTPException) as error:
            api.download_httpsms_excel("demo", {}, self.db, recipient_ids=api._safe_citizen_id("outside"))
        self.assertEqual(error.exception.status_code, 422)

    def test_polygon_holes_and_unavailable_geometry(self):
        self.add_user("in-hole", "9148682207")
        hole = [[75.4, 12.4], [75.6, 12.4], [75.6, 12.6], [75.4, 12.6], [75.4, 12.4]]
        with patch.dict(ZONE["geometry"], coordinates=[ZONE["geometry"]["coordinates"][0], hole]):
            self.assertEqual(self.preview()["affected_count"], 0)
        with patch.dict(ZONE["geometry"], coordinates=[]), self.assertRaises(HTTPException) as error:
            self.preview()
        self.assertEqual(error.exception.status_code, 422)

    def test_critical_message(self):
        self.assertEqual(generate_alert_message("CRITICAL", "Madikeri"), "LANDsense ALERT: Critical landslide risk detected near Madikeri. Move away from unstable slopes immediately and follow the recommended safer route.")

    def test_missing_sender_is_clear_and_preview_disabled(self):
        self.add_user("inside", "9148682207")
        with patch.dict("os.environ", {"HTTPSMS_FROM_NUMBER": ""}):
            self.assertFalse(self.preview()["download_enabled"])
            with self.assertRaises(HTTPException) as error:
                self.download()
        self.assertIn("Please configure HTTPSMS_FROM_NUMBER", error.exception.detail)

    def test_no_affected_or_sms_eligible_users(self):
        self.assertEqual(self.preview()["affected_count"], 0)
        self.add_user("disabled", "9148682207", enabled=0)
        self.assertEqual(self.preview()["affected_count"], 1)
        with self.assertRaises(HTTPException) as error:
            self.download()
        self.assertIn("No SMS-eligible users", error.exception.detail)

    def test_normalization_does_not_repair_invalid_numbers(self):
        for phone in ("9148682207", "919148682207", "+91 9148682207"):
            self.assertEqual(normalize_phone(phone), "+919148682207")
        for phone in ("", "+91123", "1234567890", "9148682207ext1", "=12345678", "+91９１４８６８２２０７"):
            self.assertIsNone(normalize_phone(phone))

    def test_changed_recipient_list_requires_new_preview(self):
        self.add_user("one", "9148682207")
        revision = self.preview()["revision"]
        self.add_user("two", "7795530769")
        with self.assertRaises(HTTPException) as error:
            self.download(revision=revision)
        self.assertEqual(error.exception.status_code, 409)

    def test_unknown_zone_disabled_simulation_and_low_risk(self):
        with self.assertRaises(HTTPException) as error:
            api.download_httpsms_excel("unknown", {}, self.db)
        self.assertEqual(error.exception.status_code, 404)
        with patch.object(api.simulation_mode, "read_state", return_value={"enabled": False}), self.assertRaises(HTTPException) as error:
            self.download()
        self.assertEqual(error.exception.status_code, 409)
        with patch.dict(ZONE["properties"], risk_level="LOW"), self.assertRaises(HTTPException) as error:
            self.download()
        self.assertEqual(error.exception.status_code, 422)

    def test_database_and_workbook_errors_are_clear(self):
        with patch.object(api, "_configured_zone_population", side_effect=SQLAlchemyError("private")), self.assertRaises(HTTPException) as error:
            self.download()
        self.assertEqual(error.exception.status_code, 503)
        self.assertNotIn("private", error.exception.detail)
        self.add_user("inside", "9148682207")
        with patch.object(api, "build_workbook", side_effect=RuntimeError("private")), self.assertRaises(HTTPException) as error:
            self.download()
        self.assertEqual(error.exception.status_code, 500)

    def test_http_routes_require_admin(self):
        self.add_user("inside", "9148682207")
        api.app.dependency_overrides[api.get_db] = lambda: self.db
        self.addCleanup(api.app.dependency_overrides.clear)
        with TestClient(api.app, base_url="https://testserver") as client:
            for suffix in ("httpsms-preview", "httpsms-excel"):
                url = f"/admin/affected-zones/demo/{suffix}?recipient_ids={quote(api._safe_citizen_id('inside'), safe='')}"
                self.assertEqual(client.get(url).status_code, 401)
                for role, expected in (("Citizen", 403), ("Admin", 200)):
                    with patch("backend.auth.middleware.jwt_service.decode_token", return_value={"sub": "test", "jti": "active", "role": role}), patch("backend.auth.middleware.is_user_session_active", return_value=True):
                        self.assertEqual(client.get(url, headers={"Authorization": "Bearer test"}).status_code, expected)


if __name__ == "__main__":
    unittest.main()
