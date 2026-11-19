import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

import backend_api
from backend.auth.dependencies import require_auth
from backend.auth.middleware import get_current_user, require_admin
from database.connection import get_db
from database.models import CommunityReport, CommunityReportReview


class CommunityReportHttpTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
        )
        CommunityReport.__table__.create(self.engine)
        CommunityReportReview.__table__.create(self.engine)
        self.sessions = sessionmaker(bind=self.engine, autoflush=False)
        self.role = "Citizen"
        self.citizen_uid = "citizen-1"

        def db_dependency():
            session = self.sessions()
            try:
                yield session
            finally:
                session.close()

        backend_api.app.dependency_overrides[get_db] = db_dependency
        backend_api.app.dependency_overrides[require_auth] = lambda: {
            "sub": self.citizen_uid, "role": "Citizen",
        }
        backend_api.app.dependency_overrides[get_current_user] = lambda: {
            "sub": "actor-1", "jti": "active-test-session", "role": self.role,
        }
        self.jwt_patch = patch(
            "backend.auth.middleware.jwt_service.decode_token",
            side_effect=lambda *_args, **_kwargs: {
                "sub": "actor-1", "jti": "active-test-session", "role": self.role,
            },
        )
        self.session_patch = patch("backend.auth.middleware.is_user_session_active", return_value=True)
        self.jwt_patch.start()
        self.session_patch.start()
        self.client = TestClient(backend_api.app, base_url="https://testserver")
        self.auth = {"Authorization": "Bearer community-test-token"}
        self.body = {
            "category": "landslide", "description": "Fresh soil cracks observed near the road.",
            "latitude": 12.34567, "longitude": 75.12345,
        }

    def tearDown(self):
        backend_api.app.dependency_overrides.clear()
        self.session_patch.stop()
        self.jwt_patch.stop()
        self.engine.dispose()

    def submit(self, **overrides):
        return self.client.post("/community-reports", headers=self.auth, json={**self.body, **overrides})

    def test_citizen_submission_creates_pending_report_and_initial_history(self):
        response = self.submit()
        self.assertEqual(response.status_code, 201)
        report = response.json()["report"]
        self.assertEqual(report["status"], "pending")
        self.assertEqual(report["category"], "landslide")
        self.assertNotIn("reporter_uid", report)
        detail = self.client.get(f"/community-reports/mine/{report['id']}", headers=self.auth)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["report"]["id"], report["id"])
        session = self.sessions()
        try:
            self.assertEqual(session.query(CommunityReportReview).count(), 1)
        finally:
            session.close()

    def test_unauthenticated_submission_is_rejected(self):
        response = self.client.post("/community-reports", json=self.body)
        self.assertEqual(response.status_code, 401)

    def test_invalid_category_coordinates_and_descriptions_are_rejected(self):
        for overrides in (
            {"category": "official_zone"}, {"latitude": 91}, {"longitude": -181},
            {"description": "   "}, {"description": "x" * 2001},
        ):
            with self.subTest(overrides=overrides):
                self.assertEqual(self.submit(**overrides).status_code, 422)

    def test_citizens_cannot_read_another_users_report_or_review_it(self):
        created = self.submit().json()["report"]
        self.citizen_uid = "citizen-2"
        response = self.client.get(f"/community-reports/mine/{created['id']}", headers=self.auth)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.client.post(
            f"/admin/community-reports/{created['id']}/review", headers=self.auth,
            json={"status": "verified"},
        ).status_code, 403)

    def test_admin_review_transitions_and_audit_history_are_recorded(self):
        created = self.submit().json()["report"]
        self.role = "Admin"
        first = self.client.post(
            f"/admin/community-reports/{created['id']}/review", headers=self.auth,
            json={"status": "under_review", "review_note": "Checking source details."},
        )
        self.assertEqual(first.status_code, 200)
        second = self.client.post(
            f"/admin/community-reports/{created['id']}/review", headers=self.auth,
            json={"status": "verified", "review_note": "Location and event confirmed."},
        )
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["report"]["status"], "verified")
        self.assertEqual([event["to_status"] for event in second.json()["history"]], ["pending", "under_review", "verified"])
        self.assertEqual(second.json()["history"][-1]["actor_role"], "admin")
        self.assertEqual(self.client.post(
            f"/admin/community-reports/{created['id']}/review", headers=self.auth,
            json={"status": "rejected"},
        ).status_code, 409)

    def test_admin_filters_and_pagination_and_citizen_map_separation(self):
        pending = self.submit().json()["report"]
        rejected = self.submit(category="rockfall", latitude=12.4, longitude=75.2).json()["report"]
        self.role = "Admin"
        self.assertEqual(self.client.post(
            f"/admin/community-reports/{rejected['id']}/review", headers=self.auth,
            json={"status": "rejected"},
        ).status_code, 200)
        page = self.client.get("/admin/community-reports?status=pending&limit=1&offset=0", headers=self.auth)
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.json()["total"], 1)
        self.role = "Citizen"
        map_response = self.client.get("/community-reports/map", headers=self.auth)
        self.assertEqual(map_response.status_code, 200)
        self.assertEqual([item["id"] for item in map_response.json()["reports"]], [pending["id"]])
        self.assertNotIn("description", map_response.json()["reports"][0])
        self.assertEqual(map_response.json()["reports"][0]["latitude"], round(self.body["latitude"], 3))

    def test_rapid_duplicate_and_report_rate_limit(self):
        self.assertEqual(self.submit().status_code, 201)
        self.assertEqual(self.submit().status_code, 409)
        for index in range(4):
            response = self.submit(category="rockfall", latitude=10 + index, longitude=70 + index)
            self.assertEqual(response.status_code, 201)
        self.assertEqual(self.submit(category="other", latitude=50, longitude=50).status_code, 429)


if __name__ == "__main__":
    unittest.main()
