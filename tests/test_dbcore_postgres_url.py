"""Test PostgreSQL URL detection and normalization for the database adapter.

Ensures absent URLs do not activate PostgreSQL and supported driver URLs are
converted for the legacy connection layer.
"""
from backend.dbcore import _dsn, database_url


def test_database_url_has_no_hard_coded_provider_fallback(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert database_url() is None


def test_dsn_normalizes_sqlalchemy_psycopg_url_for_legacy_adapter():
    dsn = _dsn("postgresql+psycopg://postgres:secret@localhost:5432/cafy_agent")

    assert dsn.startswith("postgresql://")
    assert "+psycopg" not in dsn
