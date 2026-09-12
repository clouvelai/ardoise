"""SQLite ledger at ~/.ardoise/ledger.db."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from ardoise import paths, prices

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  message_id TEXT NOT NULL,
  request_id TEXT NOT NULL,
  project TEXT,
  model TEXT,
  occurred_at TEXT NOT NULL,
  input_tokens INTEGER NOT NULL DEFAULT 0,
  output_tokens INTEGER NOT NULL DEFAULT 0,
  cache_creation_tokens INTEGER NOT NULL DEFAULT 0,
  cache_read_tokens INTEGER NOT NULL DEFAULT 0,
  cache_creation_5m_tokens INTEGER NOT NULL DEFAULT 0,
  cache_creation_1h_tokens INTEGER NOT NULL DEFAULT 0,
  cost_usd REAL NOT NULL DEFAULT 0,
  session_id TEXT,
  cwd TEXT,
  ingested_at TEXT NOT NULL,
  UNIQUE(message_id, request_id)
);

CREATE INDEX IF NOT EXISTS idx_entries_occurred ON entries(occurred_at);
CREATE INDEX IF NOT EXISTS idx_entries_project ON entries(project);
CREATE INDEX IF NOT EXISTS idx_entries_source ON entries(source);
CREATE INDEX IF NOT EXISTS idx_entries_month ON entries(occurred_at);

CREATE TABLE IF NOT EXISTS sources (
  path TEXT PRIMARY KEY,
  bytes INTEGER,
  mtime REAL,
  ingested_at TEXT NOT NULL
);
"""

SCHEMA_VERSION = "1"


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    paths.ensure_home()
    path = db_path or paths.ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA)
    conn.execute(
        "INSERT OR REPLACE INTO meta(key, value) VALUES ('schema_version', ?)",
        (SCHEMA_VERSION,),
    )
    return conn


@contextmanager
def session(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def upsert_entry(conn: sqlite3.Connection, row: dict[str, Any]) -> str:
    """
    Insert or keep the richer duplicate (higher output_tokens, then input_tokens).
    Returns inserted | updated | skipped.
    """
    cost = row.get("cost_usd")
    if cost is None:
        cost = prices.price_usd(
            model=row.get("model"),
            input_tokens=int(row.get("input_tokens") or 0),
            output_tokens=int(row.get("output_tokens") or 0),
            cache_read_tokens=int(row.get("cache_read_tokens") or 0),
            cache_creation_tokens=int(row.get("cache_creation_tokens") or 0),
            cache_creation_5m_tokens=int(row.get("cache_creation_5m_tokens") or 0),
            cache_creation_1h_tokens=int(row.get("cache_creation_1h_tokens") or 0),
        )
        row = {**row, "cost_usd": cost}

    payload = {
        "source": row.get("source") or "unknown",
        "message_id": str(row["message_id"]),
        "request_id": str(row["request_id"]),
        "project": row.get("project"),
        "model": row.get("model"),
        "occurred_at": row.get("occurred_at") or _now(),
        "input_tokens": int(row.get("input_tokens") or 0),
        "output_tokens": int(row.get("output_tokens") or 0),
        "cache_creation_tokens": int(row.get("cache_creation_tokens") or 0),
        "cache_read_tokens": int(row.get("cache_read_tokens") or 0),
        "cache_creation_5m_tokens": int(row.get("cache_creation_5m_tokens") or 0),
        "cache_creation_1h_tokens": int(row.get("cache_creation_1h_tokens") or 0),
        "cost_usd": float(row["cost_usd"]),
        "session_id": row.get("session_id"),
        "cwd": row.get("cwd"),
        "ingested_at": _now(),
    }
    existing = conn.execute(
        "SELECT output_tokens, input_tokens FROM entries WHERE message_id = ? AND request_id = ?",
        (payload["message_id"], payload["request_id"]),
    ).fetchone()
    if existing is None:
        conn.execute(
            """
            INSERT INTO entries (
              source, message_id, request_id, project, model, occurred_at,
              input_tokens, output_tokens, cache_creation_tokens, cache_read_tokens,
              cache_creation_5m_tokens, cache_creation_1h_tokens, cost_usd,
              session_id, cwd, ingested_at
            ) VALUES (
              :source, :message_id, :request_id, :project, :model, :occurred_at,
              :input_tokens, :output_tokens, :cache_creation_tokens, :cache_read_tokens,
              :cache_creation_5m_tokens, :cache_creation_1h_tokens, :cost_usd,
              :session_id, :cwd, :ingested_at
            )
            """,
            payload,
        )
        return "inserted"

    richer = payload["output_tokens"] > int(existing["output_tokens"]) or (
        payload["output_tokens"] == int(existing["output_tokens"])
        and payload["input_tokens"] > int(existing["input_tokens"])
    )
    if not richer:
        return "skipped"

    conn.execute(
        """
        UPDATE entries SET
          source = :source,
          project = COALESCE(:project, project),
          model = COALESCE(:model, model),
          occurred_at = :occurred_at,
          input_tokens = :input_tokens,
          output_tokens = :output_tokens,
          cache_creation_tokens = :cache_creation_tokens,
          cache_read_tokens = :cache_read_tokens,
          cache_creation_5m_tokens = :cache_creation_5m_tokens,
          cache_creation_1h_tokens = :cache_creation_1h_tokens,
          cost_usd = :cost_usd,
          session_id = COALESCE(:session_id, session_id),
          cwd = COALESCE(:cwd, cwd),
          ingested_at = :ingested_at
        WHERE message_id = :message_id AND request_id = :request_id
        """,
        payload,
    )
    return "updated"


def mark_source(conn: sqlite3.Connection, path: Path, *, bytes_: int, mtime: float) -> None:
    conn.execute(
        """
        INSERT INTO sources(path, bytes, mtime, ingested_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
          bytes = excluded.bytes,
          mtime = excluded.mtime,
          ingested_at = excluded.ingested_at
        """,
        (str(path), bytes_, mtime, _now()),
    )


def source_unchanged(conn: sqlite3.Connection, path: Path, *, bytes_: int, mtime: float) -> bool:
    row = conn.execute("SELECT bytes, mtime FROM sources WHERE path = ?", (str(path),)).fetchone()
    if row is None:
        return False
    return int(row["bytes"] or 0) == bytes_ and abs(float(row["mtime"] or 0) - mtime) < 1e-6


def count_entries(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0])
