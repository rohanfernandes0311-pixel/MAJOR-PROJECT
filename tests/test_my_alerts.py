"""Phase 5.6 tests for JWT-scoped targeted-alert retrieval."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from fastapi import HTTPException

import backend_api
from backend.auth.otp_service import authenticate_profile


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class _AlertDb:
    def __init__(self, alerts):
        self.alerts = alerts
        self.requested_users = []
        self.sql = ""

    def scalars(self, statement):
        compiled = statement.compile()
        self.sql = str(compiled)
        user_id = next(value for key, value in compiled.params.items() if "user_id" in key)
        self.requested_users.append(user_id)
        rows = sorted(
            [alert for alert in self.alerts if alert.user_id == user_id],
            key=lambda alert: alert.id,
            reverse=True,
        )
        return _Rows(rows)


class MyAlertsTests(unittest.TestCase):
    def setUp(self):
        self.db = _AlertDb([
            SimpleNamespace(id=1, user_id="user-a", risk_level="HIGH", message="A older", timestamp="2026-08-14T10:00:00Z", delivered_status="in_app_pending"),
            SimpleNamespace(id=3, user_id="user-a", risk_level="CRITICAL", message="A newer", timestamp="2026-08-14T11:00:00Z", delivered_status="in_app_pending"),
            SimpleNamespace(id=2, user_id="user-b", risk_level="MEDIUM", message="B only", timestamp="2026-08-14T10:30:00Z", delivered_status="in_app_pending"),
        ])

    def test_each_authenticated_user_sees_only_their_alerts_newest_first(self):
        user_a = backend_api.my_alerts(payload={"sub": "user-a", "role": "Citizen"}, db=self.db)
        user_b = backend_api.my_alerts(payload={"sub": "user-b", "role": "Citizen"}, db=self.db)
        admin = backend_api.my_alerts(payload={"sub": "user-a", "role": "Admin"}, db=self.db)

        self.assertEqual([alert["message"] for alert in user_a["alerts"]], ["A newer", "A older"])
        self.assertEqual([alert["message"] for alert in user_b["alerts"]], ["B only"])
        self.assertEqual(admin["count"], 2)
        self.assertNotIn("user_id", user_a["alerts"][0])
        self.assertEqual(user_a["alerts"][0]["delivery_status"], "in_app_pending")
        self.assertEqual(user_a["alerts"][0]["source_type"], "ADMIN_SIMULATION")
        self.assertTrue(all(alert.delivered_status == "in_app_pending" for alert in self.db.alerts))
        self.assertIn("ORDER BY alerts.id DESC", self.db.sql)
        self.assertEqual(self.db.requested_users, ["user-a", "user-b", "user-a"])

    def test_empty_inbox_and_no_client_user_id_parameter(self):
        result = backend_api.my_alerts(payload={"sub": "user-c"}, db=self.db)
        self.assertEqual(result, {"alerts": [], "count": 0})
        with self.assertRaises(TypeError):
            backend_api.my_alerts(payload={"sub": "user-a"}, db=self.db, user_id="user-b")

    def test_missing_or_invalid_authentication_is_rejected_by_existing_auth(self):
        with self.assertRaises(HTTPException) as missing:
            authenticate_profile(None)
        self.assertEqual(missing.exception.status_code, 401)
        with self.assertRaises(HTTPException) as invalid:
            authenticate_profile("Bearer invalid-token")
        self.assertEqual(invalid.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
