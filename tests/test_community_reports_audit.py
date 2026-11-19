import unittest
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend_api
from backend.auth.dependencies import require_auth
from backend.auth.middleware import get_current_user
from database.connection import get_db
from database.models import CommunityReport, CommunityReportReview


class CommunityReportsAuditTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        CommunityReport.__table__.create(self.engine)
        CommunityReportReview.__table__.create(self.engine)
        self.sessions = sessionmaker(bind=self.engine, autoflush=False)
        self.uid = "audit-citizen"

        def db_dependency():
            session = self.sessions()
            try:
                yield session
            finally:
                session.close()

        backend_api.app.dependency_overrides[get_db] = db_dependency
        backend_api.app.dependency_overrides[require_auth] = lambda: {"sub": self.uid, "role": "Citizen"}
        backend_api.app.dependency_overrides[get_current_user] = lambda: {
            "sub": self.uid, "role": "Citizen", "jti": "audit-session",
        }
        self.jwt_patch = patch(
            "backend.auth.middleware.jwt_service.decode_token",
            return_value={"sub": self.uid, "role": "Citizen", "jti": "audit-session"},
        )
        self.session_patch = patch("backend.auth.middleware.is_user_session_active", return_value=True)
        self.jwt_patch.start()
        self.session_patch.start()
        self.client = TestClient(backend_api.app, base_url="https://testserver")
        self.headers = {"Authorization": "Bearer audit-token"}
        self.body = {
            "category": "landslide", "description": "Cracks by the road.",
            "place_name": "Madikeri, Karnataka, India", "latitude": 12.42, "longitude": 75.73,
        }

    def tearDown(self):
        backend_api.app.dependency_overrides.clear()
        self.session_patch.stop()
        self.jwt_patch.stop()
        self.engine.dispose()

    def test_new_reports_store_place_and_authenticated_citizen_metadata(self):
        response = self.client.post("/community-reports", headers=self.headers, json=self.body)
        self.assertEqual(response.status_code, 201)
        report_id = response.json()["report"]["id"]
        session = self.sessions()
        try:
            report = session.get(CommunityReport, report_id)
            self.assertEqual(report.reporter_uid, self.uid)
            self.assertEqual(report.reporter_id, self.uid)
            self.assertEqual(report.reporter_role, "citizen")
            self.assertEqual(report.place_name, self.body["place_name"])
            self.assertEqual(report.status, "pending")
            self.assertNotIn("reporter_id", response.json()["report"])
            self.assertNotIn("place_name", response.json()["report"])
        finally:
            session.close()

    def test_report_list_contains_only_the_authenticated_citizens_reports(self):
        created = self.client.post("/community-reports", headers=self.headers, json=self.body)
        self.assertEqual(created.status_code, 201)
        self.uid = "another-audit-citizen"
        response = self.client.get("/community-reports/mine?limit=20&offset=0", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["reports"], [])
        self.assertEqual(response.json()["total"], 0)

    def test_place_tagged_report_outside_karnataka_returns_validation_error(self):
        body = {**self.body, "latitude": 19.0}
        response = self.client.post("/community-reports", headers=self.headers, json=body)
        self.assertEqual(response.status_code, 422)
        self.assertIn("within Karnataka", response.json()["detail"])

    def test_anonymous_cannot_review_reports(self):
        response = self.client.post(
            "/admin/community-reports/unknown/review", json={"status": "verified"},
        )
        self.assertEqual(response.status_code, 401)

    def test_verified_map_query_excludes_pending_and_rejected_reports(self):
        session = self.sessions()
        try:
            ids = {}
            for status in ("pending", "verified", "rejected"):
                report_id = str(uuid.uuid4())
                ids[status] = report_id
                session.add(CommunityReport(
                    id=report_id, reporter_uid=self.uid, reporter_id=self.uid,
                    reporter_role="citizen", category="landslide", description=status,
                    place_name="Madikeri", latitude=12.42, longitude=75.73,
                    submitted_at=datetime.now(timezone.utc), status=status,
                ))
            session.commit()
        finally:
            session.close()
        response = self.client.get("/community-reports/map?verified_only=true", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        reports = response.json()["reports"]
        self.assertEqual([report["id"] for report in reports], [ids["verified"]])


if __name__ == "__main__":
    unittest.main()
