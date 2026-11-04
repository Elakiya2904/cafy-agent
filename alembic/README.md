# Alembic migrations

Set `DATABASE_URL` to a local PostgreSQL database before running:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

The initial application schema migration will be added after the existing
runtime-created tables are mapped to SQLAlchemy models.
