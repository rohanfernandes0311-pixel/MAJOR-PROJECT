import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from fastapi.middleware.cors import CORSMiddleware

import backend_api


class CorsConfigurationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(backend_api.app, base_url="https://testserver")

    def test_default_local_origin_is_allowed(self):
        response = self.client.get(
            "/health", headers={"Origin": "http://localhost:5173"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers.get("access-control-allow-origin"),
            "http://localhost:5173",
        )

    def test_disallowed_origin_receives_no_cors_headers(self):
        response = self.client.get(
            "/health", headers={"Origin": "https://untrusted.example"}
        )

        self.assertEqual(response.status_code, 200)
        cors_headers = {
            name for name in response.headers if name.lower().startswith("access-control-")
        }
        self.assertEqual(cors_headers, set())

    def test_wildcard_origin_is_rejected(self):
        with patch.dict("os.environ", {"CORS_ALLOWED_ORIGINS": "*"}):
            with self.assertRaises(RuntimeError):
                backend_api._cors_allowed_origins()

    def test_cors_methods_and_headers_are_limited_to_frontend_needs(self):
        cors = next(
            middleware
            for middleware in backend_api.app.user_middleware
            if middleware.cls is CORSMiddleware
        )

        self.assertEqual(cors.kwargs["allow_methods"], ["GET", "POST", "OPTIONS"])
        self.assertEqual(cors.kwargs["allow_headers"], ["Authorization", "Content-Type"])
        self.assertFalse(cors.kwargs["allow_credentials"])


if __name__ == "__main__":
    unittest.main()
