"""Offline tests: env aliases, sb_/JWT key shapes, JWKS vs HS256 verify."""

from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives.asymmetric import ec

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ardoise_api.auth import (  # noqa: E402
    _gotrue_headers,
    decode_access_token,
    kickoff_otp,
    verify_email_otp,
)
from ardoise_api.store import Store  # noqa: E402
from ardoise_api.settings import (  # noqa: E402
    Settings,
    is_legacy_jwt_api_key,
    is_sb_api_key,
    is_usable_hs256_secret,
)
from tests.test_scaffold import _settings, _token  # noqa: E402

_JWT_SHAPED = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJyb2xlIjoiYW5vbiJ9."
    "signature-placeholder"
)


class KeyShapeTests(unittest.TestCase):
    def test_classifies_legacy_and_new_keys(self) -> None:
        self.assertTrue(is_legacy_jwt_api_key(_JWT_SHAPED))
        self.assertFalse(is_legacy_jwt_api_key("sb_publishable_abc_def"))
        self.assertTrue(is_sb_api_key("sb_publishable_abc_def"))
        self.assertTrue(is_sb_api_key("sb_secret_abc_def"))
        self.assertFalse(is_sb_api_key(_JWT_SHAPED))
        self.assertTrue(is_usable_hs256_secret("raw-hmac-secret"))
        self.assertFalse(is_usable_hs256_secret(_JWT_SHAPED))
        self.assertFalse(is_usable_hs256_secret("sb_secret_abc_def"))
        self.assertFalse(is_usable_hs256_secret(""))


class SettingsAliasTests(unittest.TestCase):
    def test_publishable_and_secret_aliases(self) -> None:
        env = {
            "SUPABASE_URL": "https://yokxvbgzcoaayahouhsd.supabase.co",
            "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_test_key",
            "SUPABASE_SECRET_KEY": "sb_secret_test_key",
        }
        with patch.dict(os.environ, env, clear=False):
            for name in (
                "SUPABASE_ANON_KEY",
                "SUPABASE_SERVICE_ROLE_KEY",
                "SUPABASE_JWT_SECRET",
            ):
                os.environ.pop(name, None)
            settings = Settings.from_env()
        self.assertEqual(
            settings.supabase_url, "https://yokxvbgzcoaayahouhsd.supabase.co"
        )
        self.assertEqual(settings.supabase_anon_key, "sb_publishable_test_key")
        self.assertEqual(settings.supabase_service_role_key, "sb_secret_test_key")
        self.assertEqual(settings.supabase_auth_key, "sb_publishable_test_key")
        self.assertTrue(settings.supabase_otp_configured)
        self.assertFalse(settings.has_hs256_secret)
        self.assertTrue(settings.jwks_url.endswith("/auth/v1/.well-known/jwks.json"))

    def test_canonical_names_win_over_aliases(self) -> None:
        env = {
            "SUPABASE_URL": "https://yokxvbgzcoaayahouhsd.supabase.co",
            "SUPABASE_ANON_KEY": "eyJ-anon",
            "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_ignored",
            "SUPABASE_SERVICE_ROLE_KEY": "eyJ-service",
            "SUPABASE_SECRET_KEY": "sb_secret_ignored",
        }
        with patch.dict(os.environ, env, clear=False):
            settings = Settings.from_env()
        self.assertEqual(settings.supabase_anon_key, "eyJ-anon")
        self.assertEqual(settings.supabase_service_role_key, "eyJ-service")

    def test_jwt_shaped_secret_is_not_hs256(self) -> None:
        env = {
            "SUPABASE_URL": "https://yokxvbgzcoaayahouhsd.supabase.co",
            "SUPABASE_JWT_SECRET": _JWT_SHAPED,
        }
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("SUPABASE_ANON_KEY", None)
            os.environ.pop("SUPABASE_PUBLISHABLE_KEY", None)
            settings = Settings.from_env()
        self.assertFalse(settings.has_hs256_secret)
        self.assertFalse(settings.supabase_otp_configured)


class GotrueHeaderTests(unittest.TestCase):
    def test_apikey_for_sb_and_legacy(self) -> None:
        sb = _settings(
            supabase_url="https://yokxvbgzcoaayahouhsd.supabase.co",
            supabase_anon_key="sb_publishable_test_key",
        )
        headers = _gotrue_headers(sb)
        self.assertEqual(headers["apikey"], "sb_publishable_test_key")
        self.assertEqual(headers["Authorization"], "Bearer sb_publishable_test_key")

        legacy = _settings(
            supabase_url="https://yokxvbgzcoaayahouhsd.supabase.co",
            supabase_anon_key=_JWT_SHAPED,
        )
        legacy_headers = _gotrue_headers(legacy)
        self.assertEqual(legacy_headers["apikey"], _JWT_SHAPED)
        self.assertEqual(legacy_headers["Authorization"], f"Bearer {_JWT_SHAPED}")


class OtpMockPathTests(unittest.TestCase):
    def test_missing_keys_stay_mocked(self) -> None:
        settings = _settings(supabase_anon_key="", supabase_url="")
        result = kickoff_otp(settings, "human@example.com")
        self.assertTrue(result["mocked"])
        self.assertTrue(result["ok"])

    def test_url_without_key_stays_mocked(self) -> None:
        settings = _settings(
            supabase_url="https://yokxvbgzcoaayahouhsd.supabase.co",
            supabase_anon_key="",
        )
        result = kickoff_otp(settings, "human@example.com")
        self.assertTrue(result["mocked"])

    def test_jwt_shaped_secret_does_not_mint_mock_session(self) -> None:
        settings = _settings(
            supabase_url="",
            supabase_anon_key="",
            supabase_jwt_secret=_JWT_SHAPED,
        )
        store = Store(":memory:")
        result = verify_email_otp(
            settings, store, "human@example.com", token="123456"
        )
        self.assertTrue(result["mocked"])
        self.assertFalse(result.get("access_token"))
        self.assertIn("not configured", result["detail"])


class JwtVerifyTests(unittest.TestCase):
    def test_hs256_when_raw_secret_present(self) -> None:
        settings = _settings()
        claims = decode_access_token(settings, _token())
        self.assertEqual(claims["email"], "smoke@example.com")

    def test_jwks_when_token_has_kid_and_no_hs256_secret(self) -> None:
        private_key = ec.generate_private_key(ec.SECP256R1())
        now = int(time.time())
        token = jwt.encode(
            {
                "aud": "authenticated",
                "role": "authenticated",
                "sub": "user-es256",
                "email": "es256@example.com",
                "iss": "https://yokxvbgzcoaayahouhsd.supabase.co/auth/v1",
                "exp": now + 3600,
                "iat": now,
            },
            private_key,
            algorithm="ES256",
            headers={"kid": "ardoise-test-key"},
        )
        settings = _settings(
            supabase_url="https://yokxvbgzcoaayahouhsd.supabase.co",
            supabase_jwt_secret="",
            supabase_anon_key="sb_publishable_test_key",
        )
        self.assertFalse(settings.has_hs256_secret)

        class _Key:
            key = private_key.public_key()

        class _Client:
            def get_signing_key_from_jwt(self, given: str) -> _Key:
                assert given == token
                return _Key()

        with patch("ardoise_api.auth._jwks_client", return_value=_Client()):
            claims = decode_access_token(settings, token)
        self.assertEqual(claims["email"], "es256@example.com")
        self.assertEqual(claims["sub"], "user-es256")

    def test_jwt_shaped_secret_falls_through_to_jwks(self) -> None:
        private_key = ec.generate_private_key(ec.SECP256R1())
        now = int(time.time())
        token = jwt.encode(
            {
                "aud": "authenticated",
                "sub": "user-kid",
                "email": "kid@example.com",
                "iss": "https://yokxvbgzcoaayahouhsd.supabase.co/auth/v1",
                "exp": now + 3600,
            },
            private_key,
            algorithm="ES256",
            headers={"kid": "only-key-id"},
        )
        settings = _settings(
            supabase_url="https://yokxvbgzcoaayahouhsd.supabase.co",
            supabase_jwt_secret=_JWT_SHAPED,
        )
        self.assertFalse(settings.has_hs256_secret)

        class _Key:
            key = private_key.public_key()

        class _Client:
            def get_signing_key_from_jwt(self, given: str) -> _Key:
                return _Key()

        with patch("ardoise_api.auth._jwks_client", return_value=_Client()):
            claims = decode_access_token(settings, token)
        self.assertEqual(claims["sub"], "user-kid")


if __name__ == "__main__":
    unittest.main()
