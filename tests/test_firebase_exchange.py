import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException
from sqlalchemy.exc import OperationalError

from backend.auth.firebase_verify import exchange_firebase_token
from backend.auth.router import FirebaseExchangeRequest, post_firebase_exchange


class FirebaseExchangeTests(unittest.TestCase):
    @patch("backend.auth.firebase_verify.otp_store.log_login_history")
    @patch("backend.auth.firebase_verify.otp_store.create_user_session")
    @patch("backend.auth.firebase_verify.jwt_service.issue_auth_tokens")
    @patch("backend.auth.firebase_verify.upsert_user")
    @patch("backend.auth.firebase_verify.get_user")
    @patch("backend.auth.firebase_verify.verify_firebase_id_token")
    def test_existing_user_is_reused_and_session_is_created(
        self, verify, get_user, upsert_user, issue_tokens, create_session, log_login
    ) -> None:
        verify.return_value = {"uid": "existing-uid", "phone_number": "+919876543210"}
        get_user.return_value = {"uid": "existing-uid", "role": "Admin"}
        issue_tokens.return_value = {
            "token_type": "bearer",
            "access_token": "access",
            "refresh_token": "refresh",
            "access_jti": "jti",
            "access_expires_in_minutes": 15,
        }

        result = exchange_firebase_token("verified-token", device_hash="device")

        get_user.assert_called_once_with("existing-uid")
        upsert_user.assert_called_once()
        create_session.assert_called_once()
        log_login.assert_called_once()
        self.assertEqual(result["profile"]["role"], "Admin")

    @patch("backend.auth.firebase_verify.otp_store.log_login_history")
    @patch("backend.auth.firebase_verify.otp_store.create_user_session")
    @patch("backend.auth.firebase_verify.jwt_service.issue_auth_tokens")
    @patch("backend.auth.firebase_verify.upsert_user")
    @patch("backend.auth.firebase_verify.get_user", return_value=None)
    @patch("backend.auth.firebase_verify.verify_firebase_id_token")
    def test_new_verified_user_is_created_as_citizen_without_duplication_logic(
        self, verify, get_user, upsert_user, issue_tokens, create_session, log_login
    ) -> None:
        verify.return_value = {"uid": "new-uid", "phone_number": "+919876543210"}
        issue_tokens.return_value = {
            "token_type": "bearer",
            "access_token": "access",
            "refresh_token": "refresh",
            "access_jti": "jti",
            "access_expires_in_minutes": 15,
        }

        result = exchange_firebase_token("verified-token")

        upsert_user.assert_called_once()
        create_session.assert_called_once()
        log_login.assert_called_once()
        self.assertEqual(result["profile"]["role"], "Citizen")

    @patch("backend.auth.router.exchange_firebase_token")
    def test_database_failure_returns_safe_503_and_creates_no_fake_session(self, exchange) -> None:
        exchange.side_effect = OperationalError("SELECT", {}, Exception("database unavailable"))
        request = Mock(client=Mock(host="127.0.0.1"), headers={})

        with self.assertRaises(HTTPException) as raised:
            post_firebase_exchange(
                FirebaseExchangeRequest(id_token="x" * 100),
                request,
            )

        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(
            raised.exception.detail,
            "Unable to complete sign-in right now. Please try again.",
        )

    @patch("backend.auth.router.exchange_firebase_token", side_effect=ValueError("invalid token"))
    def test_invalid_firebase_token_remains_unauthorized(self, exchange) -> None:
        request = Mock(client=Mock(host="127.0.0.1"), headers={})

        with self.assertRaises(HTTPException) as raised:
            post_firebase_exchange(FirebaseExchangeRequest(id_token="x" * 100), request)

        self.assertEqual(raised.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
