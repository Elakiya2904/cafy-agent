"""Test isolation: never touch the developer's or production database.

* The app's default database is redirected to a throw-away file (SQLite) or throw-away schema (Postgres).
* With DATABASE_URL pointing at a non-local host the suite refuses to run, unless explicitly allowed.
"""
import os
import tempfile
from urllib.parse import urlparse

import pytest

url = os.getenv("DATABASE_URL") or ""
host = urlparse(url).hostname if url else None
if url and host not in ("localhost", "127.0.0.1", "::1", None) and os.getenv("CAFY_ALLOW_REMOTE_TEST_DB") != "1":
    pytest.exit(f"Refusing to run tests against remote database host '{host}'. Use a local Postgres "
                "(DATABASE_URL=postgresql://localhost/cafy_test) or set CAFY_ALLOW_REMOTE_TEST_DB=1 for a disposable project.", returncode=2)

_tmp = tempfile.mkdtemp(prefix="cafy-tests-")
os.environ["CAFY_DB_PATH"] = os.path.join(_tmp, "app-under-test.db")
os.environ.pop("APP_ENV", None)
