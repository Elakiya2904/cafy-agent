"""Verify a migration: compare the original database with the Docker one, table by table. Read-only on both.

Checks every table's row count, the alembic revision, and an exact content checksum for each table in the
public schema (where the application data lives). Exit code 0 means everything matched.

    .venv\\Scripts\\python.exe docker\\compare_databases.py
    .venv\\Scripts\\python.exe docker\\compare_databases.py --source <url> --target <url>

Defaults: source = DATABASE_URL in .env; target = the compose db on 127.0.0.1:POSTGRES_HOST_PORT.
Passwords are never printed.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import quote

import psycopg
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def _plain(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def _redact(url: str) -> str:
    head, _, tail = url.partition("@")
    return (head.split(":")[0] + ":" + head.split(":")[1] + ":****@" + tail) if tail else url


def snapshot(url: str) -> dict:
    with psycopg.connect(_plain(url), connect_timeout=10) as conn:
        conn.read_only = True
        cur = conn.cursor()
        # Render values identically on both servers (Windows and Linux servers differ in time zone and
        # collation), so content checksums compare data, not formatting.
        cur.execute("set TimeZone = 'UTC'; set DateStyle = 'ISO, YMD'; set IntervalStyle = 'postgres'; "
                    "set extra_float_digits = 3; set bytea_output = 'hex'")
        cur.execute("""select table_schema, table_name from information_schema.tables
                       where table_type = 'BASE TABLE' and table_schema not in ('pg_catalog', 'information_schema')
                       order by 1, 2""")
        tables = cur.fetchall()
        counts, checksums = {}, {}
        for schema, name in tables:
            ident = f'"{schema}"."{name}"'
            cur.execute(f"select count(*) from {ident}")
            counts[f"{schema}.{name}"] = cur.fetchone()[0]
            if schema == "public":
                # Order by each row's own hash: independent of the server's collation rules.
                cur.execute(
                    f"select md5(coalesce(string_agg(md5(t::text), '' order by md5(t::text)), '')) from {ident} t"
                )
                checksums[f"{schema}.{name}"] = cur.fetchone()[0]
        revision = None
        cur.execute("select to_regclass('public.alembic_version')")
        if cur.fetchone()[0]:
            cur.execute("select string_agg(version_num, ',') from alembic_version")
            revision = cur.fetchone()[0]
        return {"counts": counts, "checksums": checksums, "revision": revision}


def main() -> int:
    env = dotenv_values(ROOT / ".env")
    default_target = "postgresql://{u}:{p}@127.0.0.1:{port}/{db}".format(
        u=quote(env.get("POSTGRES_USER") or "cafy", safe=""),
        p=quote(env.get("POSTGRES_PASSWORD") or "", safe=""),
        port=env.get("POSTGRES_HOST_PORT") or "5433",
        db=env.get("POSTGRES_DB") or "cafy_agent",
    )
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", default=env.get("DATABASE_URL") or "")
    parser.add_argument("--target", default=default_target)
    args = parser.parse_args()
    if not args.source:
        print("No source database: set DATABASE_URL in .env or pass --source.")
        return 2

    print("source:", _redact(_plain(args.source)))
    print("target:", _redact(_plain(args.target)))
    src, dst = snapshot(args.source), snapshot(args.target)

    problems = []
    if src["revision"] != dst["revision"]:
        problems.append(f"alembic revision differs: {src['revision']} vs {dst['revision']}")
    for table in sorted(set(src["counts"]) | set(dst["counts"])):
        a, b = src["counts"].get(table), dst["counts"].get(table)
        if a != b:
            problems.append(f"{table}: rows {a} vs {b}")
        elif table in src["checksums"] and src["checksums"][table] != dst["checksums"].get(table):
            problems.append(f"{table}: same row count but different content")

    public = {t: n for t, n in src["counts"].items() if t.startswith("public.")}
    print(f"tables: {len(src['counts'])} source / {len(dst['counts'])} target")
    print(f"rows:   {sum(src['counts'].values())} source / {sum(dst['counts'].values())} target")
    print(f"alembic revision: {src['revision']} / {dst['revision']}")
    print("public tables with data (content checksums compared):")
    for table, n in sorted(public.items()):
        if n:
            mark = "OK " if (dst["counts"].get(table) == n and dst["checksums"].get(table) == src["checksums"][table]) else "BAD"
            print(f"  [{mark}] {table}: {n}")
    if problems:
        print(f"\nMISMATCHES ({len(problems)}):")
        for p in problems[:50]:
            print("  -", p)
        return 1
    print("\nAll tables match (row counts, and exact content for every public table).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
