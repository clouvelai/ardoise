"""Store selection: SQLite when DATABASE_URL is unset, Postgres when set."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ardoise_api.main import create_app  # noqa: E402
from ardoise_api.pgstore import PostgresStore, normalize_database_url  # noqa: E402
from ardoise_api.settings import Settings  # noqa: E402
from ardoise_api.store import Store, UnavailableStore, open_store  # noqa: E402
from tests.test_scaffold import _settings  # noqa: E402

PG_DSN = "postgresql://ardoise:secret@127.0.0.1:5432/ardoise_test"


class _RecordingConn:
    def __init__(self, fetchone_values: list[object] | None = None) -> None:
        self.sql: list[tuple[str, object]] = []
        self._fetchone_values = list(fetchone_values or [])

    def execute(self, sql: str, params: object = None) -> MagicMock:
        self.sql.append((sql, params))
        result = MagicMock()

        def _fetchone() -> object:
            if self._fetchone_values:
                return self._fetchone_values.pop(0)
            return None

        result.fetchone.side_effect = _fetchone
        return result

    def __enter__(self) -> _RecordingConn:
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False


class _DownStore:
    kind = "postgres"

    def ping(self) -> None:
        raise OSError("could not connect to postgresql://ardoise:secret@db.example/x")


class NormalizeUrlTests(unittest.TestCase):
    def test_postgres_scheme_and_remote_ssl(self) -> None:
        raw = "postgres://u:p@db.example.supabase.co:5432/postgres"
        out = normalize_database_url(raw)
        self.assertTrue(out.startswith("postgresql://"))
        self.assertIn("sslmode=require", out)
        self.assertIn("u:p@", out)

    def test_localhost_does_not_force_ssl(self) -> None:
        raw = "postgresql://u:p@127.0.0.1:5432/ardoise"
        self.assertEqual(normalize_database_url(raw), raw)

    def test_existing_sslmode_kept(self) -> None:
        raw = "postgresql://u:p@db.example.com:5432/postgres?sslmode=verify-full"
        self.assertEqual(normalize_database_url(raw), raw)


class OpenStoreTests(unittest.TestCase):
    def test_unset_database_url_uses_sqlite(self) -> None:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        self.addCleanup(lambda: os.path.exists(tmp.name) and os.unlink(tmp.name))
        store = open_store(_settings(database_url="", sqlite_path=tmp.name))
        self.assertEqual(store.kind, "sqlite")
        self.assertIsInstance(store, Store)
        store.ping()

    def test_blank_database_url_uses_sqlite(self) -> None:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        self.addCleanup(lambda: os.path.exists(tmp.name) and os.unlink(tmp.name))
        store = open_store(_settings(database_url="   ", sqlite_path=tmp.name))
        self.assertEqual(store.kind, "sqlite")

    def test_database_url_selects_postgres(self) -> None:
        conn = _RecordingConn()
        with patch("ardoise_api.pgstore.psycopg.connect", return_value=conn):
            store = open_store(
                _settings(database_url=PG_DSN, sqlite_path="/tmp/ardoise-unused.db")
            )
        self.assertEqual(store.kind, "postgres")
        self.assertIsInstance(store, PostgresStore)
        self.assertNotIn("secret", repr(store))

    def test_from_env_strips_database_url(self) -> None:
        env = {"DATABASE_URL": f"  {PG_DSN}  "}
        with patch.dict(os.environ, env, clear=False):
            settings = Settings.from_env()
        self.assertEqual(settings.database_url, PG_DSN)

    def test_missing_psycopg_is_unavailable_postgres(self) -> None:
        with patch.dict(sys.modules, {"ardoise_api.pgstore": None}):
            store = open_store(_settings(database_url=PG_DSN))
        self.assertIsInstance(store, UnavailableStore)
        self.assertEqual(store.kind, "postgres")
        with self.assertRaises(RuntimeError):
            store.ping()


class CreateAppStoreTests(unittest.TestCase):
    def test_create_app_defaults_to_sqlite_without_database_url(self) -> None:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        self.addCleanup(lambda: os.path.exists(tmp.name) and os.unlink(tmp.name))
        app = create_app(settings=_settings(database_url="", sqlite_path=tmp.name))
        self.assertEqual(app.state.store.kind, "sqlite")
        body = TestClient(app).get("/health").json()
        self.assertEqual(body["store"], "sqlite")
        self.assertTrue(body["store_ok"])
        self.assertTrue(body["ok"])
        self.assertFalse(body["database_url_configured"])

    def test_create_app_defaults_to_postgres_when_database_url(self) -> None:
        conn = _RecordingConn()
        with patch("ardoise_api.pgstore.psycopg.connect", return_value=conn):
            app = create_app(settings=_settings(database_url=PG_DSN))
            self.assertEqual(app.state.store.kind, "postgres")
            body = TestClient(app).get("/health").json()
        self.assertEqual(body["store"], "postgres")
        self.assertTrue(body["database_url_configured"])
        self.assertTrue(body["store_ok"])
        self.assertTrue(body["ok"])
        ping_sql = " ".join(sql for sql, _ in conn.sql).lower()
        self.assertIn("ops.accounts", ping_sql)
        self.assertNotIn("secret", json.dumps(body))
        self.assertNotIn("postgresql://", json.dumps(body))

    def test_health_honest_when_postgres_ping_fails(self) -> None:
        settings = _settings(database_url=PG_DSN)
        app = create_app(settings=settings, store=_DownStore())
        res = TestClient(app).get("/health")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        dumped = json.dumps(body)
        self.assertEqual(body["store"], "postgres")
        self.assertTrue(body["database_url_configured"])
        self.assertFalse(body["store_ok"])
        self.assertFalse(body["ok"])
        self.assertEqual(body["store_error"], "OSError")
        self.assertNotIn("secret", dumped)
        self.assertNotIn("postgresql://", dumped.lower())


class PostgresStoreSqlTests(unittest.TestCase):
    def test_upsert_and_fulfill_use_ops_schema(self) -> None:
        account = {
            "id": "11111111-1111-1111-1111-111111111111",
            "external_key": "a@example.com",
            "email": "a@example.com",
            "supabase_sub": "sub",
            "plan": "free",
        }
        session = {
            "id": "22222222-2222-2222-2222-222222222222",
            "account_id": account["id"],
            "stripe_session_id": "cs_test_1",
            "credits": 2000,
            "status": "open",
            "fulfilled_at": None,
            "mode": "payment",
            "plan": None,
        }
        conn = _RecordingConn(
            [
                None,  # existing account
                account,  # select after insert
                session,  # fulfill select
                None,  # existing credit
            ]
        )
        with patch("ardoise_api.pgstore.psycopg.connect", return_value=conn):
            store = PostgresStore(PG_DSN)
            row = store.upsert_account(
                external_key="a@example.com",
                email="a@example.com",
                supabase_sub="sub",
            )
            self.assertEqual(row["id"], account["id"])
            result = store.fulfill_checkout(
                "cs_test_1", stripe_customer_id="cus_1"
            )
        self.assertTrue(result["ok"])
        joined = "\n".join(sql for sql, _ in conn.sql)
        self.assertIn("ops.accounts", joined)
        self.assertIn("ops.customers", joined)
        self.assertIn("ops.checkout_sessions", joined)
        self.assertIn("ops.credit_ledger", joined)
        self.assertIn("%s", joined)
        self.assertNotIn("?", joined)


if __name__ == "__main__":
    unittest.main()
