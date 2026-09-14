"""Offline scaffold tests: health + mock Checkout + JWT session."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import jwt
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ardoise_api.main import create_app  # noqa: E402
from ardoise_api.settings import Settings  # noqa: E402
from ardoise_api.store import Store  # noqa: E402

JWT_SECRET = "test-supabase-jwt-secret-for-local-smoke"


def _settings(**overrides: object) -> Settings:
    env = {
        "env": "development",
        "public_url": "http://127.0.0.1:8787",
        "web_origin": "http://localhost:3000",
        "supabase_url": "https://example.supabase.co",
        "supabase_anon_key": "",
        "supabase_jwt_secret": JWT_SECRET,
        "database_url": "",
        "sqlite_path": "",
        "stripe_secret_key": "",
        "stripe_webhook_secret": "",
        "stripe_price_lookup_key": "ardoise_credits_20",
        "stripe_price_id": "",
        "stripe_mock_flag": True,
        "default_amount_cents": 2000,
        "default_credits": 2000,
        "lab_bypass_flag": False,
        "checkout_success_url": "http://localhost:3000/billing/success",
        "checkout_cancel_url": "http://localhost:3000/billing/cancel",
    }
    env.update(overrides)
    return Settings(**env)  # type: ignore[arg-type]


def _token(email: str = "smoke@example.com", sub: str = "user-smoke") -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "aud": "authenticated",
            "role": "authenticated",
            "sub": sub,
            "email": email,
            "iss": "https://example.supabase.co/auth/v1",
            "exp": now + 3600,
            "iat": now,
        },
        JWT_SECRET,
        algorithm="HS256",
    )


def _client(**overrides: object) -> TestClient:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    settings = _settings(**overrides)
    app = create_app(settings=settings, store=Store(tmp.name))
    client = TestClient(app)
    client._db_path = tmp.name  # type: ignore[attr-defined]
    return client


class ScaffoldTests(unittest.TestCase):
    def tearDown(self) -> None:
        path = getattr(self, "_db", None)
        if path and os.path.exists(path):
            os.unlink(path)

    def _cli(self, **overrides: object) -> TestClient:
        client = _client(**overrides)
        self._db = getattr(client, "_db_path", None)
        return client

    def test_health_reports_mock(self) -> None:
        client = self._cli()
        res = client.get("/health")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["service"], "ardoise-api")
        self.assertTrue(body["stripe_mock"])
        self.assertFalse(body["lab_auth_bypass"])
        self.assertFalse(body["supabase_otp_configured"])
        self.assertEqual(body["store"], "sqlite")
        self.assertTrue(body["store_ok"])
        self.assertFalse(body["database_url_configured"])
        self.assertNotIn("store_error", body)

    def test_me_requires_bearer(self) -> None:
        client = self._cli()
        self.assertEqual(client.get("/v1/me").status_code, 401)

    def test_me_with_jwt(self) -> None:
        client = self._cli()
        res = client.get("/v1/me", headers={"Authorization": f"Bearer {_token()}"})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["account"]["external_key"], "smoke@example.com")
        self.assertEqual(body["account"]["plan"], "free")
        self.assertFalse(body["account"]["invoice_grade"])
        self.assertEqual(body["credits"], 0)

    def test_lab_bypass_off_by_default(self) -> None:
        client = self._cli()
        res = client.get("/v1/me", headers={"X-Ardoise-Lab-User": "lab@example.com"})
        self.assertEqual(res.status_code, 401)

    def test_lab_bypass_gated(self) -> None:
        client = self._cli(lab_bypass_flag=True)
        res = client.get("/v1/me", headers={"X-Ardoise-Lab-User": "lab@example.com"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["account"]["external_key"], "lab@example.com")

    def test_lab_bypass_ignored_in_production(self) -> None:
        client = self._cli(lab_bypass_flag=True, env="production")
        res = client.get("/v1/me", headers={"X-Ardoise-Lab-User": "lab@example.com"})
        self.assertEqual(res.status_code, 401)

    def test_otp_mocked_without_supabase(self) -> None:
        client = self._cli()
        res = client.post("/v1/auth/otp", json={"email": "human@example.com"})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["mocked"])

    def test_otp_verify_mocked_mints_session(self) -> None:
        client = self._cli()
        res = client.post(
            "/v1/auth/otp/verify",
            json={"email": "human@example.com", "token": "123456"},
        )
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertTrue(body["mocked"])
        self.assertTrue(body["access_token"])
        self.assertEqual(body["account"]["plan"], "free")
        me = client.get(
            "/v1/me", headers={"Authorization": f"Bearer {body['access_token']}"}
        )
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["account"]["email"], "human@example.com")
        self.assertFalse(me.json()["account"]["invoice_grade"])

    def test_otp_verify_not_configured_without_jwt_secret(self) -> None:
        client = self._cli(supabase_jwt_secret="")
        res = client.post(
            "/v1/auth/otp/verify",
            json={"email": "human@example.com", "token": "123456"},
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["mocked"])
        self.assertFalse(body.get("access_token"))
        self.assertIn("not configured", body["detail"])

    def test_otp_verify_rejects_bad_email(self) -> None:
        client = self._cli()
        res = client.post(
            "/v1/auth/otp/verify", json={"email": "nope", "token": "123456"}
        )
        self.assertEqual(res.status_code, 400)

    def test_otp_verify_token_hash_mocked_is_400(self) -> None:
        client = self._cli()
        res = client.post("/v1/auth/otp/verify", json={"token_hash": "abc"})
        self.assertEqual(res.status_code, 400)

    def test_mock_checkout_and_fulfill_idempotent(self) -> None:
        client = self._cli()
        headers = {"Authorization": f"Bearer {_token()}"}
        created = client.post("/v1/checkout/sessions", json={}, headers=headers)
        self.assertEqual(created.status_code, 200, created.text)
        session = created.json()
        self.assertTrue(session["mock"])
        self.assertEqual(session["mode"], "payment")
        self.assertTrue(session["url"].endswith(session["stripe_session_id"]))
        self.assertEqual(session["credits"], 2000)
        sid = session["stripe_session_id"]
        self.assertTrue(sid.startswith("cs_mock_"))

        page = client.get(f"/v1/checkout/mock/{sid}")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Mock Checkout", page.text)

        event = {
            "type": "checkout.session.completed",
            "data": {"object": {"id": sid, "customer": "cus_mock"}},
        }
        hook = client.post("/v1/stripe/webhook", content=json.dumps(event))
        self.assertEqual(hook.status_code, 200)
        self.assertTrue(hook.json()["ok"])
        self.assertFalse(hook.json()["already_fulfilled"])

        again = client.post("/v1/stripe/webhook", content=json.dumps(event))
        self.assertEqual(again.status_code, 200)
        self.assertTrue(again.json()["already_fulfilled"])

        me = client.get("/v1/me", headers=headers).json()
        self.assertEqual(me["credits"], 2000)

    def test_webhook_signature_when_not_mock(self) -> None:
        secret = "whsec_test"
        client = self._cli(
            stripe_mock_flag=False,
            stripe_secret_key="sk_test_placeholder",
            stripe_webhook_secret=secret,
        )
        # Pre-insert a session via store
        store: Store = client.app.state.store
        account = store.upsert_account(
            external_key="pay@example.com",
            email="pay@example.com",
            supabase_sub="user-pay",
        )
        store.insert_checkout(
            account_id=account["id"],
            stripe_session_id="cs_live_1",
            amount_cents=2000,
            credits=2000,
            currency="usd",
            checkout_url="https://checkout.stripe.com/c/pay/cs_live_1",
        )
        payload = json.dumps(
            {
                "type": "checkout.session.completed",
                "data": {"object": {"id": "cs_live_1", "customer": "cus_1"}},
            }
        ).encode("utf-8")
        ts = int(time.time())
        sig = hmac.new(
            secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256
        ).hexdigest()
        bad = client.post("/v1/stripe/webhook", content=payload)
        self.assertEqual(bad.status_code, 400)
        ok = client.post(
            "/v1/stripe/webhook",
            content=payload,
            headers={"Stripe-Signature": f"t={ts},v1={sig}"},
        )
        self.assertEqual(ok.status_code, 200)
        self.assertTrue(ok.json()["ok"])

    def test_settings_reads_stripe_price_pro_and_team(self) -> None:
        with patch.dict(
            os.environ,
            {
                "STRIPE_PRICE_PRO": "price_1UFItuLXeKVxcTxwwvakV7CI",
                "STRIPE_PRICE_TEAM": "price_1UFIu0LXeKVxcTxwN5l52Fzf",
                "STRIPE_PRICE_BUSINESS": "price_should_be_ignored",
            },
            clear=False,
        ):
            settings = Settings.from_env()
        self.assertEqual(
            settings.stripe_price_pro, "price_1UFItuLXeKVxcTxwwvakV7CI"
        )
        self.assertEqual(
            settings.stripe_price_team, "price_1UFIu0LXeKVxcTxwN5l52Fzf"
        )
        self.assertFalse(hasattr(settings, "stripe_price_business"))

    def test_billing_checkout_requires_auth(self) -> None:
        client = self._cli()
        res = client.post("/v1/billing/checkout", json={"plan": "team"})
        self.assertEqual(res.status_code, 401)

    def test_billing_checkout_rejects_free(self) -> None:
        client = self._cli()
        res = client.post(
            "/v1/billing/checkout",
            json={"plan": "free"},
            headers={"Authorization": f"Bearer {_token()}"},
        )
        self.assertEqual(res.status_code, 400)

    def test_billing_subscription_checkout_and_fulfill(self) -> None:
        client = self._cli()
        headers = {"Authorization": f"Bearer {_token()}"}
        created = client.post(
            "/v1/billing/checkout", json={"plan": "team"}, headers=headers
        )
        self.assertEqual(created.status_code, 200, created.text)
        session = created.json()
        self.assertTrue(session["mock"])
        self.assertEqual(session["mode"], "subscription")
        self.assertEqual(session["plan"], "team")
        self.assertEqual(session["amount_cents"], 4900)
        sid = session["stripe_session_id"]

        page = client.get(f"/v1/checkout/mock/{sid}")
        self.assertEqual(page.status_code, 200)
        self.assertIn("team", page.text)

        event = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": sid,
                    "customer": "cus_team",
                    "subscription": "sub_team",
                    "metadata": {"plan": "team"},
                }
            },
        }
        hook = client.post("/v1/billing/webhook", content=json.dumps(event))
        self.assertEqual(hook.status_code, 200)
        self.assertTrue(hook.json()["ok"])
        self.assertEqual(hook.json()["plan"], "team")

        me = client.get("/v1/me", headers=headers).json()
        self.assertEqual(me["account"]["plan"], "team")
        self.assertTrue(me["account"]["invoice_grade"])
        self.assertEqual(me["credits"], 0)

        again = client.post("/v1/billing/webhook", content=json.dumps(event))
        self.assertEqual(again.status_code, 200)
        self.assertTrue(again.json()["already_fulfilled"])

    def test_pro_plan_is_invoice_grade(self) -> None:
        client = self._cli()
        headers = {"Authorization": f"Bearer {_token()}"}
        created = client.post(
            "/v1/billing/checkout", json={"plan": "pro"}, headers=headers
        )
        self.assertEqual(created.status_code, 200, created.text)
        self.assertEqual(created.json()["plan"], "pro")
        self.assertEqual(created.json()["amount_cents"], 2000)
        sid = created.json()["stripe_session_id"]
        hook = client.post(
            "/v1/billing/webhook",
            content=json.dumps(
                {
                    "type": "checkout.session.completed",
                    "data": {
                        "object": {
                            "id": sid,
                            "customer": "cus_pro",
                            "metadata": {"plan": "pro"},
                        }
                    },
                }
            ),
        )
        self.assertEqual(hook.status_code, 200)
        me = client.get("/v1/me", headers=headers).json()
        self.assertEqual(me["account"]["plan"], "pro")
        self.assertTrue(me["account"]["invoice_grade"])

    def test_mock_complete_html_redirects_to_success(self) -> None:
        client = self._cli()
        headers = {"Authorization": f"Bearer {_token()}"}
        created = client.post(
            "/v1/billing/checkout", json={"plan": "pro"}, headers=headers
        )
        sid = created.json()["stripe_session_id"]
        res = client.post(
            f"/v1/checkout/mock/{sid}/complete",
            headers={"accept": "text/html"},
            follow_redirects=False,
        )
        self.assertEqual(res.status_code, 303)
        self.assertTrue(res.headers["location"].endswith("/billing/success"))
        me = client.get("/v1/me", headers=headers).json()
        self.assertEqual(me["account"]["plan"], "pro")

    def test_billing_checkout_rejects_business(self) -> None:
        client = self._cli()
        res = client.post(
            "/v1/billing/checkout",
            json={"plan": "business"},
            headers={"Authorization": f"Bearer {_token()}"},
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("pro or team", res.json()["detail"])

    def test_usage_sync_and_status(self) -> None:
        client = self._cli()
        headers = {"Authorization": f"Bearer {_token()}"}
        secret = client.post(
            "/v1/usage/sync",
            json={"rows": [{"message_id": "m1", "prompt": "nope"}]},
            headers=headers,
        )
        self.assertEqual(secret.status_code, 400)

        res = client.post(
            "/v1/usage/sync",
            json={
                "rows": [
                    {
                        "source": "anthropic_t0",
                        "vendor": "anthropic",
                        "message_id": "m1",
                        "request_id": "r1",
                        "project": "acme/one",
                        "model": "claude-sonnet-4-6",
                        "occurred_at": "2026-09-02T12:00:00Z",
                        "input_tokens": 10,
                        "output_tokens": 4,
                        "cost_usd": 0.02,
                        "tier": "T0",
                        "cycle": "2026-09",
                    }
                ]
            },
            headers=headers,
        )
        self.assertEqual(res.status_code, 200, res.text)
        self.assertTrue(res.json()["ok"])
        self.assertEqual(res.json()["upserted"], 1)

        again = client.post(
            "/v1/usage/sync",
            json={
                "rows": [
                    {
                        "message_id": "m1",
                        "request_id": "r1",
                        "source": "anthropic_t0",
                        "vendor": "anthropic",
                        "project": "acme/one",
                        "occurred_at": "2026-09-02T12:00:00Z",
                        "cost_usd": 0.03,
                        "tier": "T0",
                        "cycle": "2026-09",
                    }
                ]
            },
            headers=headers,
        )
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json()["upserted"], 1)

        status = client.get("/v1/usage/status?month=2026-09", headers=headers)
        self.assertEqual(status.status_code, 200)
        body = status.json()
        self.assertEqual(body["month_entries"], 1)
        self.assertFalse(body["invoice_grade"])
        self.assertEqual(body["section_a"], [])
        self.assertIn("Free", " ".join(body.get("notes") or []))

        stmt = client.get("/v1/usage/statement?month=2026-09", headers=headers)
        self.assertEqual(stmt.status_code, 200)
        self.assertIn("Estimated", stmt.json()["markdown"])
        doc = stmt.json().get("document") or {}
        self.assertEqual(doc.get("title"), "Statement")
        self.assertEqual((doc.get("from") or {}).get("name"), "Ardoise")
        self.assertIn("groups", doc)
        self.assertIn("totals", doc)
        self.assertFalse((doc.get("totals") or {}).get("show_reconciliation"))
        self.assertNotIn("Amount due", str(doc))
        self.assertTrue(any("spend statement" in m for m in (doc.get("memo") or [])))
        self.assertIn("period", doc)
        self.assertIn("| Description | Quantity | Rate | Amount |", stmt.json()["markdown"])

        minted = client.post("/v1/cli/tokens", headers=headers)
        self.assertEqual(minted.status_code, 200)
        token = minted.json()["token"]
        self.assertTrue(token.startswith("ard_"))
        cli_status = client.get(
            "/v1/usage/status?month=2026-09",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(cli_status.status_code, 200)
        self.assertEqual(cli_status.json()["month_entries"], 1)

        forbidden = client.post(
            "/v1/invoices",
            json={"vendor": "anthropic", "cycle": "2026-09", "usd_cents": 1200},
            headers=headers,
        )
        self.assertEqual(forbidden.status_code, 403)

    def test_pro_invoice_grade_statement(self) -> None:
        client = self._cli()
        headers = {"Authorization": f"Bearer {_token('pro@example.com', 'user-pro')}"}
        checkout = client.post(
            "/v1/billing/checkout",
            json={"plan": "pro"},
            headers=headers,
        )
        self.assertEqual(checkout.status_code, 200)
        sid = checkout.json()["stripe_session_id"]
        client.post(f"/v1/checkout/mock/{sid}/complete")
        client.post(
            "/v1/usage/sync",
            json={
                "rows": [
                    {
                        "message_id": "p1",
                        "request_id": "p1",
                        "vendor": "anthropic",
                        "source": "anthropic_t0",
                        "project": "acme/one",
                        "occurred_at": "2026-09-02T12:00:00Z",
                        "input_tokens": 100,
                        "output_tokens": 20,
                        "cost_usd": 1.5,
                        "tier": "T0",
                        "cycle": "2026-09",
                    }
                ],
                "invoices": [
                    {
                        "vendor": "anthropic",
                        "cycle": "2026-09",
                        "usd_cents": 1950,
                        "source": "paste",
                    }
                ],
            },
            headers=headers,
        )
        status = client.get("/v1/usage/status?month=2026-09", headers=headers)
        self.assertTrue(status.json()["invoice_grade"])
        self.assertEqual(status.json()["billed_usd"], 19.5)
        self.assertEqual(status.json()["section_a"][0]["tier_of_truth"], "invoice")
        stmt = client.get("/v1/usage/statement?month=2026-09", headers=headers)
        self.assertIn("19.50", stmt.json()["markdown"])
        doc = stmt.json().get("document") or {}
        self.assertTrue(doc.get("invoice_grade"))
        self.assertEqual(float(doc.get("total_usd") or 0), 19.5)
        self.assertTrue(doc.get("groups"))
        vendors = {row.get("vendor") for row in doc.get("groups") or []}
        self.assertIn("anthropic", vendors)
        self.assertEqual((doc.get("prepared_for") or {}).get("email"), "pro@example.com")
        memo = " ".join(doc.get("memo") or [])
        self.assertIn("spend statement", memo)
        self.assertNotIn("Amount due", str(doc))
        adj = (doc.get("groups") or [{}])[0].get("adjustment")
        self.assertTrue(adj)
        totals = doc.get("totals") or {}
        self.assertTrue(totals.get("show_reconciliation"))
        self.assertIn("List price", stmt.json()["markdown"])
        self.assertIn("Reconciling adjustment", stmt.json()["markdown"])
        pasted = client.post(
            "/v1/invoices",
            json={"vendor": "cursor", "cycle": "2026-09", "usd_cents": 400},
            headers=headers,
        )
        self.assertEqual(pasted.status_code, 200)


if __name__ == "__main__":
    unittest.main()
