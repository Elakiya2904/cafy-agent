"""Database access layer: Postgres (Supabase) in production, SQLite for offline development.

The application SQL is written once, in SQLite style (``?`` placeholders, ``rowid``...).
When ``DATABASE_URL`` is set, ``PgConnection`` translates that SQL to Postgres on the fly and
exposes the same small connection API the services use, so both back-ends run the same code.
"""
import hashlib
import logging
import os
import re
import sqlite3
import threading
from typing import Any, Dict, Iterable, List, Optional, Sequence
from urllib.parse import urlparse

logger = logging.getLogger("cafy.dbcore")

SCHEMA_LOCK_KEY = 727274  # pg_advisory_xact_lock key so concurrent cold starts don't race on DDL


class Row(dict):
    """A dict that also supports positional access, like ``sqlite3.Row``."""

    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


def database_url() -> Optional[str]:
    return (os.getenv("DATABASE_URL") or "").strip() or None


def is_postgres() -> bool:
    return database_url() is not None


# --------------------------------------------------------------------------- SQL translation
def translate_sql(sql: str) -> str:
    """SQLite-style statement -> Postgres. Quoted strings are left untouched."""
    out: List[str] = []
    i, n = 0, len(sql)
    while i < n:
        ch = sql[i]
        if ch == "'":
            j = i + 1
            while j < n:
                if sql[j] == "'" and j + 1 < n and sql[j + 1] == "'":
                    j += 2
                    continue
                if sql[j] == "'":
                    break
                j += 1
            out.append(sql[i:j + 1].replace("%", "%%"))
            i = j + 1
            continue
        out.append("%s" if ch == "?" else "%%" if ch == "%" else ch)
        i += 1
    text = "".join(out)
    text = re.sub(r"\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b", "BIGSERIAL PRIMARY KEY", text, flags=re.I)
    text = re.sub(r"\bREAL\b", "DOUBLE PRECISION", text)
    text = re.sub(r"\bBLOB\b", "BYTEA", text)
    text = re.sub(r"\bLIKE\b", "ILIKE", text)
    text = re.sub(r"\browid\b", "seq", text, flags=re.I)
    text = re.sub(r"lower\(hex\(randomblob\(16\)\)\)", "md5(random()::text || clock_timestamp()::text)", text, flags=re.I)
    return text


def split_statements(script: str) -> List[str]:
    return [s.strip() for s in script.split(";") if s.strip()]


# --------------------------------------------------------------------------- cursors / connections
class PgCursor:
    def __init__(self, raw):
        self._c = raw
        self.lastrowid = None

    def _wrap(self, row):
        return Row(row) if row is not None else None

    def execute(self, sql: str, args: Sequence[Any] = ()):
        self._c.execute(translate_sql(sql), tuple(args))
        return self

    def executemany(self, sql: str, seq: Iterable[Sequence[Any]]):
        self._c.executemany(translate_sql(sql), [tuple(a) for a in seq])
        return self

    def fetchone(self):
        return self._wrap(self._c.fetchone()) if self._c.description else None

    def fetchall(self):
        return [Row(r) for r in self._c.fetchall()] if self._c.description else []

    def __iter__(self):
        return iter(self.fetchall())

    @property
    def rowcount(self):
        return self._c.rowcount


class PgConnection:
    """sqlite3-compatible surface over a pooled psycopg2 connection."""

    backend = "postgres"

    def __init__(self, pool, raw, schema: str):
        self._pool, self._raw, self._schema, self._closed = pool, raw, schema, False

    def cursor(self) -> PgCursor:
        from psycopg2.extras import RealDictCursor
        return PgCursor(self._raw.cursor(cursor_factory=RealDictCursor))

    def execute(self, sql: str, args: Sequence[Any] = ()) -> PgCursor:
        return self.cursor().execute(sql, args)

    def executemany(self, sql: str, seq: Iterable[Sequence[Any]]) -> PgCursor:
        return self.cursor().executemany(sql, seq)

    def executescript(self, script: str) -> None:
        cur = self.cursor()
        for stmt in split_statements(script):
            cur.execute(stmt)

    def add_column_if_missing(self, table: str, column: str, ddl_type: str) -> None:
        self.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {ddl_type}")

    def commit(self) -> None:
        self._raw.commit()

    def rollback(self) -> None:
        self._raw.rollback()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._raw.rollback()  # discard anything uncommitted before the connection is reused
        except Exception:
            pass
        self._pool.putconn(self._raw)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            self.commit() if exc_type is None else self.rollback()
        finally:
            self.close()
        return False


class SqliteConnection(sqlite3.Connection):
    """sqlite3 connection with the small extras the services rely on."""

    backend = "sqlite"

    def add_column_if_missing(self, table: str, column: str, ddl_type: str) -> None:
        existing = {row[1] for row in self.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            self.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}")


# --------------------------------------------------------------------------- pool
_pools: Dict[str, Any] = {}
_pool_lock = threading.Lock()


def _dsn(url: str) -> str:
    host = urlparse(url).hostname or ""
    if "sslmode=" not in url and host not in ("localhost", "127.0.0.1", "::1", ""):
        url += ("&" if "?" in url else "?") + "sslmode=require"  # Supabase only accepts TLS
    return url


def _pool_for(url: str):
    with _pool_lock:
        if url not in _pools:
            from psycopg2.pool import ThreadedConnectionPool
            _pools[url] = ThreadedConnectionPool(1, int(os.getenv("DB_POOL_MAX", "10")), _dsn(url), connect_timeout=10)
        return _pools[url]


def schema_for(db_path: str, default_path: str) -> str:
    """Production uses ``public``; any other SQLite-style path gets its own isolated schema (used by tests)."""
    if os.path.abspath(db_path) == os.path.abspath(default_path):
        return "public"
    return "t_" + hashlib.sha1(os.path.abspath(db_path).encode()).hexdigest()[:12]


def connect(db_path: str, default_path: str):
    url = database_url()
    if not url:
        conn = sqlite3.connect(db_path, timeout=15, factory=SqliteConnection)
        conn.row_factory = sqlite3.Row
        return conn
    schema = schema_for(db_path, default_path)
    pool = _pool_for(url)
    raw = pool.getconn()
    try:
        with raw.cursor() as cur:
            if schema != "public":
                cur.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
            cur.execute(f'SET search_path TO "{schema}", public')
        raw.commit()
    except Exception:
        pool.putconn(raw)
        raise
    return PgConnection(pool, raw, schema)


def lock_schema(conn) -> None:
    """Serialise schema creation across concurrent instances (Postgres only)."""
    if getattr(conn, "backend", "") == "postgres":
        conn.execute("SELECT pg_advisory_xact_lock(?)", (SCHEMA_LOCK_KEY,))
