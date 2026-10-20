#!/usr/bin/env python3
"""Apply Evid's versioned PostgreSQL migrations exactly once per database."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.src.runtime import load_environment


def main():
    load_environment(ROOT)
    if os.getenv("EVID_STORAGE_BACKEND", "local").lower() != "r2_neon":
        print("Database migrations skipped: local storage backend.")
        return
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required when EVID_STORAGE_BACKEND=r2_neon.")
    import psycopg
    migration_dir = ROOT / "deploy" / "migrations"
    with psycopg.connect(database_url) as conn, conn.cursor() as cur:
        cur.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
            name TEXT PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )""")
        for migration in sorted(migration_dir.glob("*.sql")):
            cur.execute("SELECT 1 FROM schema_migrations WHERE name = %s", (migration.name,))
            if cur.fetchone():
                continue
            cur.execute(migration.read_text())
            cur.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (migration.name,))
            print(f"Applied {migration.name}")


if __name__ == "__main__":
    main()
