"""One-time migration: fix user_profiles and user_resume_files tables in PostgreSQL.

Run with:
    uv run backend/scripts/fix_user_tables.py

This is safe to run multiple times (all operations are idempotent).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

import psycopg2
from backend.dbcore import _dsn, database_url

url = database_url()
if not url:
    print("ERROR: DATABASE_URL is not set.")
    sys.exit(1)

conn = psycopg2.connect(_dsn(url))
conn.autocommit = True  # run each statement independently so DDL is immediately visible
cur = conn.cursor()

migrations = [
    # ── user_profiles ──────────────────────────────────────────────────────
    # Add candidate_id if missing
    """
    DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name='user_profiles' AND column_name='candidate_id'
        ) THEN
            ALTER TABLE user_profiles ADD COLUMN candidate_id TEXT;
        END IF;
    END $$;
    """,
    # Add resume_json if missing
    """
    DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name='user_profiles' AND column_name='resume_json'
        ) THEN
            ALTER TABLE user_profiles ADD COLUMN resume_json TEXT;
        END IF;
    END $$;
    """,
    # Add updated_at if missing
    """
    DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name='user_profiles' AND column_name='updated_at'
        ) THEN
            ALTER TABLE user_profiles ADD COLUMN updated_at TEXT NOT NULL DEFAULT '';
        END IF;
    END $$;
    """,
    # Add unique constraint on candidate_id (needed for ON CONFLICT)
    """
    DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'user_profiles_candidate_id_key'
        ) THEN
            ALTER TABLE user_profiles ADD CONSTRAINT user_profiles_candidate_id_key UNIQUE (candidate_id);
        END IF;
    END $$;
    """,

    # ── user_resume_files ──────────────────────────────────────────────────
    """
    DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name='user_resume_files' AND column_name='candidate_id'
        ) THEN
            ALTER TABLE user_resume_files ADD COLUMN candidate_id TEXT;
        END IF;
    END $$;
    """,
    """
    DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name='user_resume_files' AND column_name='filename'
        ) THEN
            ALTER TABLE user_resume_files ADD COLUMN filename TEXT NOT NULL DEFAULT '';
        END IF;
    END $$;
    """,
    """
    DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name='user_resume_files' AND column_name='content_type'
        ) THEN
            ALTER TABLE user_resume_files ADD COLUMN content_type TEXT NOT NULL DEFAULT '';
        END IF;
    END $$;
    """,
    """
    DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name='user_resume_files' AND column_name='size_bytes'
        ) THEN
            ALTER TABLE user_resume_files ADD COLUMN size_bytes INTEGER NOT NULL DEFAULT 0;
        END IF;
    END $$;
    """,
    """
    DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name='user_resume_files' AND column_name='content'
        ) THEN
            ALTER TABLE user_resume_files ADD COLUMN content BYTEA;
        END IF;
    END $$;
    """,
    """
    DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name='user_resume_files' AND column_name='parsed_resume'
        ) THEN
            ALTER TABLE user_resume_files ADD COLUMN parsed_resume TEXT;
        END IF;
    END $$;
    """,
    """
    DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name='user_resume_files' AND column_name='uploaded_at'
        ) THEN
            ALTER TABLE user_resume_files ADD COLUMN uploaded_at TEXT NOT NULL DEFAULT '';
        END IF;
    END $$;
    """,
    # Unique constraint on candidate_id for ON CONFLICT support
    """
    DO $$ BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'user_resume_files_candidate_id_key'
        ) THEN
            ALTER TABLE user_resume_files ADD CONSTRAINT user_resume_files_candidate_id_key UNIQUE (candidate_id);
        END IF;
    END $$;
    """,
]

print(f"Connected to: {url[:40]}...")
for i, sql in enumerate(migrations, 1):
    try:
        cur.execute(sql)
        print(f"  [{i}/{len(migrations)}] OK")
    except Exception as e:
        print(f"  [{i}/{len(migrations)}] FAILED: {e}")
        sys.exit(1)

cur.close()
conn.close()
print("\nMigration complete. Restart the backend.")
