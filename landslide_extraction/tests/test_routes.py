from __future__ import annotations

import io
from pathlib import Path
from unittest import TestCase, mock

from fastapi.testclient import TestClient

from backend_api import app


FIXTURES = Path(__file__).resolve().parent / "fixtures"


class RouteTests(TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.secure_headers = {"x-forwarded-proto": "https"}

    def test_existing_route_still_works(self):
        response = self.client.get("/health", headers=self.secure_headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_corrupt_pdf_returns_clean_400(self):
        response = self.client.post(
            "/landslide-extraction/jobs",
            headers=self.secure_headers,
            files={"file": ("corrupt.pdf", io.BytesIO(b"not a real pdf"), "application/pdf")},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("detail", response.json())

    def test_module_exception_isolated_from_existing_routes(self):
        with mock.patch("landslide_extraction.background.extract_tabular_inventory", side_effect=RuntimeError("boom")):
            with (FIXTURES / "blank_one_page.pdf").open("rb") as handle:
                response = self.client.post(
                    "/landslide-extraction/jobs",
                    headers=self.secure_headers,
                    files={"file": ("blank_one_page.pdf", handle, "application/pdf")},
                )
        self.assertEqual(response.status_code, 202)
        self.assertIn("job_id", response.json())
        self.assertEqual(self.client.get("/health", headers=self.secure_headers).status_code, 200)
