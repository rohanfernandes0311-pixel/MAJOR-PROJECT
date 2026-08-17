"""Phase 5.4 recipient-preview tests without writing to the runtime database."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from fastapi import HTTPException

import backend_api
from backend.auth.middleware import get_current_user, require_admin


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _PreviewDb:
    def __init__(self, rows, risks):
        self.rows = rows
        self.risks = iter(risks)

    def execute(self, _statement):
        return _Rows(self.rows)

    def scalar(self, _statement):
        return next(self.risks, None)


class _ActivationDb(_PreviewDb):
    def __init__(self, rows, values, existing_user_ids=()):
        super().__init__(rows, values)
        self.existing_user_ids = list(existing_user_ids)
        self.created = []
        self.commits = 0

    def scalars(self, _statement):
        return _Rows(self.existing_user_ids)

    def add_all(self, alerts):
        self.created.extend(alerts)

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass


class AffectedZonePreviewTests(unittest.TestCase):
    def _request(self, zone_id="RGD-01"):
        return backend_api.AffectedZonePreviewRequest(
            zone_id=zone_id,
            risk_level="high",
            message="Preview only",
            duration_minutes=60,
        )

    def test_existing_zone_returns_only_users_inside_polygon(self):
        rows = [
            (SimpleNamespace(uid="inside-1", phone_number="+919876543210"), SimpleNamespace(latitude=18.4, longitude=73.29, last_updated="2026-08-14T10:00:00Z")),
            (SimpleNamespace(uid="outside-1", phone_number="+919999999999"), SimpleNamespace(latitude=19.0, longitude=74.0, last_updated="2026-08-14T10:01:00Z")),
            (SimpleNamespace(uid="inside-2", phone_number="+918888888888"), SimpleNamespace(latitude=18.45, longitude=73.25, last_updated="2026-08-14T10:02:00Z")),
        ]
        result = backend_api.preview_affected_zone_recipients(self._request(), {"role": "Admin"}, _PreviewDb(rows, [3, "HIGH", "MEDIUM"]))

        self.assertTrue(result["preview_only"])
        self.assertEqual(result["source_type"], "ADMIN_SIMULATION")
        self.assertEqual(result["affected_zone"]["zone_id"], "RGD-01")
        self.assertEqual(result["recipient_count"], 2)
        self.assertEqual([item["user_id"] for item in result["recipients"]], ["inside-1", "inside-2"])
        self.assertNotIn("phone_number", result["recipients"][0])

    def test_empty_preview_and_unknown_zone(self):
        outside = [(SimpleNamespace(uid="outside", phone_number="+919999999999"), SimpleNamespace(latitude=19.0, longitude=74.0, last_updated="now"))]
        result = backend_api.preview_affected_zone_recipients(self._request(), {"role": "Admin"}, _PreviewDb(outside, [1]))
        self.assertEqual(result["recipient_count"], 0)

        with self.assertRaises(HTTPException) as error:
            backend_api.preview_affected_zone_recipients(self._request("unknown"), {"role": "Admin"}, _PreviewDb([], []))
        self.assertEqual(error.exception.status_code, 404)

    def test_admin_role_guard_rejects_missing_invalid_and_citizen(self):
        with self.assertRaises(HTTPException) as missing:
            get_current_user(None)
        self.assertEqual(missing.exception.status_code, 401)

        with self.assertRaises(HTTPException) as invalid:
            get_current_user("Bearer invalid-token")
        self.assertEqual(invalid.exception.status_code, 401)

        with self.assertRaises(HTTPException) as citizen:
            require_admin({"role": "Citizen"})
        self.assertEqual(citizen.exception.status_code, 403)
        self.assertEqual(require_admin({"role": "Admin"})["role"], "Admin")

    def test_activation_creates_only_server_calculated_recipients(self):
        rows = [
            (SimpleNamespace(uid="inside", phone_number="+919876543210"), SimpleNamespace(latitude=18.4, longitude=73.29, last_updated="now")),
            (SimpleNamespace(uid="outside", phone_number="+919999999999"), SimpleNamespace(latitude=19.0, longitude=74.0, last_updated="now")),
        ]
        db = _ActivationDb(rows, [2, "HIGH"])
        # The request rejects arbitrary user IDs, and activation independently
        # recalculates membership from current server-side locations.
        with self.assertRaises(Exception):
            backend_api.AffectedZonePreviewRequest(
                zone_id="RGD-01", risk_level="high", message="Preview only", duration_minutes=60, user_ids=["outside"]
            )
        request = self._request()
        result = backend_api.activate_affected_zone_alert(request, {"role": "Admin"}, db)

        self.assertEqual(result["recipient_count"], 1)
        self.assertEqual(result["status"], "in_app_pending")
        self.assertFalse(result["external_sms_sent"])
        self.assertEqual([alert.user_id for alert in db.created], ["inside"])
        self.assertEqual(db.created[0].risk_level, "HIGH")
        self.assertEqual(db.created[0].message, "Preview only")
        self.assertEqual(db.created[0].delivered_status, "in_app_pending")
        self.assertEqual(db.commits, 1)

    def test_activation_empty_and_duplicate_recipients_create_no_alerts(self):
        outside = [(SimpleNamespace(uid="outside", phone_number="+919999999999"), SimpleNamespace(latitude=19.0, longitude=74.0, last_updated="now"))]
        empty_db = _ActivationDb(outside, [1])
        empty = backend_api.activate_affected_zone_alert(self._request(), {"role": "Admin"}, empty_db)
        self.assertEqual(empty["status"], "no_recipients")
        self.assertEqual(empty_db.created, [])

        inside = [(SimpleNamespace(uid="inside", phone_number="+919876543210"), SimpleNamespace(latitude=18.4, longitude=73.29, last_updated="now"))]
        duplicate_db = _ActivationDb(inside, [1, "HIGH"], existing_user_ids=["inside"])
        duplicate = backend_api.activate_affected_zone_alert(self._request(), {"role": "Admin"}, duplicate_db)
        self.assertEqual(duplicate["status"], "deduplicated")
        self.assertEqual(duplicate["deduplicated_count"], 1)
        self.assertEqual(duplicate_db.created, [])


if __name__ == "__main__":
    unittest.main()
