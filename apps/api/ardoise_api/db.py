"""Store selection: Postgres when DATABASE_URL is set, else SQLite.

Production must not silently fall back to SQLite if DATABASE_URL is present
but unreachable. Force SQLite only when the URL is unset or
``ARDOISE_API_STORE=sqlite``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from ardoise_api.settings import Settings
from ardoise_api.store import Store

log = logging.getLogger("ardoise_api.db")

_DRIVER_PREFIXES = (
    "postgresql+asyncpg://",
    "postgresql+psycopg2://",
    "postgresql+psycopg://",
    "postgres+asyncpg://",
    "postgres+psycopg2://",
    "postgres+psycopg://",
    "postgres://",
)

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
_SSL_HOST_SUFFIXES = (
    ".supabase.co",
    ".supabase.com",
    ".pooler.supabase.com",
    ".proxy.rlwy.net",
    ".rlwy.net",
)


def default_sqlite_path(settings: Settings) -> str:
    if settings.sqlite_path:
        return settings.sqlite_path
    here = Path(__file__).resolve().parent.parent / ".data" / "local.db"
    return str(here)


def normalize_database_url(url: str) -> str:
    """Strip quotes and SQLAlchemy/async driver prefixes for psycopg."""
    url = (url or "").strip()
    if len(url) >= 2 and url[0] == url[-1] and url[0] in {"'", '"'}:
        url = url[1:-1].strip()
    lower = url.lower()
    for prefix in _DRIVER_PREFIXES:
        if lower.startswith(prefix):
            return "postgresql://" + url[len(prefix) :]
    return url


def _with_sslmode(url: str, mode: str) -> str:
    parsed = urlparse(url)
    query = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() != "sslmode"
    ]
    query.append(("sslmode", mode))
    return urlunparse(parsed._replace(query=urlencode(query)))


def _hostname(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def apply_ssl_hints(url: str) -> str:
    """Add sslmode=require for known hosted hosts when the URL omits it."""
    parsed = urlparse(url)
    if any(k.lower() == "sslmode" for k, _ in parse_qsl(parsed.query, keep_blank_values=True)):
        return url
    host = _hostname(url)
    if not host or host in _LOCAL_HOSTS or host.endswith(".railway.internal"):
        return url
    if any(host.endswith(suffix) for suffix in _SSL_HOST_SUFFIXES):
        return _with_sslmode(url, "require")
    return url


def choose_backend(settings: Settings) -> str:
    """Return ``sqlite`` or ``postgres`` without connecting."""
    force = (settings.store_force or "").strip().lower()
    url = (settings.database_url or "").strip()
    if force in {"sqlite", "sqlite3"}:
        return "sqlite"
    if url.lower().startswith("sqlite:"):
        return "sqlite"
    if force in {"postgres", "postgresql"}:
        if not url:
            raise RuntimeError("ARDOISE_API_STORE=postgres but DATABASE_URL is unset")
        return "postgres"
    if url:
        return "postgres"
    return "sqlite"


def _psycopg_connect(dsn: str) -> Any:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError(
            "DATABASE_URL is set but the psycopg package is not installed. "
            "Install apps/api requirements (psycopg[binary])."
        ) from exc
    return psycopg.connect(dsn, connect_timeout=10, row_factory=dict_row)


def open_postgres(url: str) -> tuple[Any, str]:
    """Connect and return ``(connection, working_dsn)``.

    Retries once with ``sslmode=require`` when the first attempt fails and
    the URL did not already pin sslmode. Never logs the DSN (it has a password).
    """
    dsn = apply_ssl_hints(normalize_database_url(url))
    try:
        return _psycopg_connect(dsn), dsn
    except RuntimeError:
        # Missing driver / explicit config errors — do not mask with an SSL retry.
        raise
    except Exception as exc:
        retry = _with_sslmode(dsn, "require")
        if retry == dsn:
            raise
        log.warning(
            "Postgres connect failed (%s); retrying with sslmode=require",
            type(exc).__name__,
        )
        return _psycopg_connect(retry), retry


def connect_postgres(dsn: str) -> Any:
    """Open a connection using an already-resolved DSN (no extra SSL retry)."""
    return _psycopg_connect(dsn)


def open_store(settings: Settings) -> Store:
    backend = choose_backend(settings)
    if backend == "sqlite":
        if (settings.store_force or "").strip().lower() in {"sqlite", "sqlite3"} and (
            settings.database_url or ""
        ).strip():
            log.info(
                "store=sqlite (ARDOISE_API_STORE=%s overrides DATABASE_URL)",
                settings.store_force,
            )
        else:
            log.info("store=sqlite (DATABASE_URL unset)")
        return Store(default_sqlite_path(settings))

    url = (settings.database_url or "").strip()
    try:
        store = Store(database_url=url)
    except Exception as exc:
        log.exception(
            "DATABASE_URL is set but Postgres connect failed; "
            "refusing silent SQLite fallback"
        )
        raise RuntimeError(
            "DATABASE_URL is set but Postgres is unreachable. "
            "Fix the connection (host, password, sslmode, network) or set "
            "ARDOISE_API_STORE=sqlite to force SQLite."
        ) from exc
    log.info("store=postgres")
    return store
