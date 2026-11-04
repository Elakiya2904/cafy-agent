import pytest

from backend.sqlalchemy_db import build_engine


def test_build_engine_uses_psycopg_driver():
    engine = build_engine("postgresql://postgres:secret@localhost:5432/cafy_agent")

    assert engine.url.drivername == "postgresql+psycopg"
    assert engine.url.host == "localhost"
    assert engine.url.database == "cafy_agent"
    assert engine.url.password == "secret"


def test_build_engine_rejects_non_postgres_urls():
    with pytest.raises(ValueError):
        build_engine("sqlite:///tmp/cafy.db")
