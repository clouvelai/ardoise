"""Offline store selection: DATABASE_URL → Postgres, otherwise SQLite."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.pop("DATABASE_URL", None)
os.environ.pop("ARDOISE_API_STORE", None)

from fastapi.testclient import TestClient  # noqa: E402

from ardoise_api.db import (  # noqa: E402
    apply_ssl_hints,
    choose_backend,
    normalize_database_url,
    open_store,
)
from ardoise_api.main import create_app  # noqa: E402
from ardoise_api.settings import Settings  # noqa: E402
from ardoise_api.store import Store  # noqa: E402
from tests.test_scaffold import _settings  # noqa: E402


class NormalizeUrlTests(unittest.TestCase):
    def test_rewrites_asyncpg_and_postgres_schemes(self) -> None:
        creds = "user:pass@db.example:5432/app"
        self.assertEqual(
            normalize_database_url(f"postgres://{creds}"),
            f"postgresql://{creds}",
        )
        self.assertEqual(
            normalize_database_url(f"postgresql+asyncpg://{creds}"),
            f"postgresql://{creds}",
        )
        self.assertEqual(
            normalize_database_url(f"postgresql+psycopg://{creds}?sslmode=require"),
            f"postgresql://{creds}?sslmode=require",
        )
        self.assertEqual(
            normalize_database_url(f"postgresql://{creds}"),
            f"postgresql://{creds}",
        )

    def test_strips_quotes_and_whitespace(self) -> None:
        raw = '  "postgresql://user:pass@h/db"  '
        self.assertEqual(normalize_database_url(raw), "postgresql://user:pass@h/db")

    def test_ssl_hint_for_supabase_not_local(self) -> None:
        hosted = "postgresql://u:p@db.abc.supabase.co:5432/postgres"
        self.assertIn("sslmode=require", apply_ssl_hints(hosted))
        local = "postgresql://u:p@127.0.0.1:5432/app"
        self.assertEqual(apply_ssl_hints(local), local)
        internal = "postgresql://u:p@postgres.railway.internal:5432/railway"
        self.assertEqual(apply_ssl_hints(internal), internal)
        already = hosted + "?sslmode=disable"
        self.assertEqual(apply_ssl_hints(already), already)


class SettingsEnvTests(unittest.TestCase):
    def test_from_env_reads_database_url_and_store_force(self) -> None:
        env = {
            "DATABASE_URL": "  postgresql://u:p@h/db  ",
            "ARDOISE_API_STORE": "sqlite",
        }
        with patch.dict(os.environ, env, clear=False):
            settings = Settings.from_env()
        self.assertEqual(settings.database_url, "postgresql://u:p@h/db")
        self.assertEqual(settings.store_force, "sqlite")
        self.assertEqual(choose_backend(settings), "sqlite")


class ChooseBackendTests(unittest.TestCase):
    def test_unset_url_is_sqlite(self) -> None:
        self.assertEqual(choose_backend(_settings()), "sqlite")

    def test_database_url_selects_postgres(self) -> None:
        self.assertEqual(
            choose_backend(_settings(database_url="postgresql://u:p@h/db")),
            "postgres",
        )

    def test_force_sqlite_overrides_url(self) -> None:
        self.assertEqual(
            choose_backend(
                _settings(
                    database_url="postgresql://u:p@h/db",
                    store_force="sqlite",
                )
            ),
            "sqlite",
        )

    def test_force_postgres_without_url_raises(self) -> None:
        with self.assertRaises(RuntimeError) as ctx:
            choose_backend(_settings(store_force="postgres"))
        self.assertIn("DATABASE_URL", str(ctx.exception))

    def test_sqlite_scheme_stays_sqlite(self) -> None:
        self.assertEqual(
            choose_backend(_settings(database_url="sqlite:////tmp/x.db")),
            "sqlite",
        )


class OpenStoreTests(unittest.TestCase):
    def test_open_store_sqlite_when_unset(self) -> None:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        self.addCleanup(lambda: os.path.exists(tmp.name) and os.unlink(tmp.name))
        store = open_store(_settings(sqlite_path=tmp.name))
        self.assertEqual(store.backend, "sqlite")
        self.assertEqual(store.path, tmp.name)

    def test_force_sqlite_skips_postgres_connect(self) -> None:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        self.addCleanup(lambda: os.path.exists(tmp.name) and os.unlink(tmp.name))
        with patch("ardoise_api.db.open_postgres") as pg:
            store = open_store(
                _settings(
                    database_url="postgresql://u:p@127.0.0.1:1/db",
                    sqlite_path=tmp.name,
                    store_force="sqlite",
                )
            )
        pg.assert_not_called()
        self.assertEqual(store.backend, "sqlite")

    def test_database_url_connect_failure_is_loud(self) -> None:
        with patch(
            "ardoise_api.db.open_postgres",
            side_effect=OSError("connection refused"),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                open_store(_settings(database_url="postgresql://u:p@127.0.0.1:1/db"))
        msg = str(ctx.exception)
        self.assertIn("DATABASE_URL", msg)
        self.assertIn("unreachable", msg)
        self.assertNotIn("sqlite fallback succeeded", msg.lower())

    def test_missing_psycopg_is_loud(self) -> None:
        with patch(
            "ardoise_api.db._psycopg_connect",
            side_effect=RuntimeError("psycopg package is not installed"),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                open_store(_settings(database_url="postgresql://u:p@h/db"))
        self.assertIn("DATABASE_URL", str(ctx.exception))

    def test_successful_postgres_open(self) -> None:
        raw = MagicMock()
        with patch("ardoise_api.db.open_postgres", return_value=(raw, "postgresql://u:p@h/db")):
            store = open_store(_settings(database_url="postgresql://u:p@h/db"))
        self.assertEqual(store.backend, "postgres")
        raw.execute.assert_called()
        raw.commit.assert_called()
        raw.close.assert_called()


class HealthStoreTests(unittest.TestCase):
    def test_health_reports_sqlite_backend(self) -> None:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        self.addCleanup(lambda: os.path.exists(tmp.name) and os.unlink(tmp.name))
        app = create_app(settings=_settings(sqlite_path=tmp.name))
        body = TestClient(app).get("/health").json()
        self.assertEqual(body["store"], "sqlite")
        self.assertFalse(body["database_url_configured"])

    def test_health_reports_injected_postgres_backend(self) -> None:
        store = MagicMock()
        store.backend = "postgres"
        app = create_app(
            settings=_settings(database_url="postgresql://u:p@h/db"),
            store=store,
        )
        body = TestClient(app).get("/health").json()
        self.assertEqual(body["store"], "postgres")
        self.assertTrue(body["database_url_configured"])


class SqliteStoreStillWorks(unittest.TestCase):
    def test_memory_store_roundtrip(self) -> None:
        store = Store(":memory:")
        self.assertEqual(store.backend, "sqlite")
        account = store.upsert_account(
            external_key="a@example.com",
            email="a@example.com",
            supabase_sub="sub-a",
        )
        self.assertEqual(account["email"], "a@example.com")
        self.assertEqual(store.credit_balance(account["id"]), 0)


if __name__ == "__main__":
    unittest.main()
