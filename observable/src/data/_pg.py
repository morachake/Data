"""
_pg.py — lightweight Postgres helper for Observable Framework data loaders.

Usage from any loader in src/data/:
    from _pg import query, query_one

Do NOT import serving/db.py here – that pulls in Streamlit.
Loaders run from the repo root (the cwd Observable sets), so we walk up from
__file__ to find .env when relative look-up fails.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# ── Locate .env ───────────────────────────────────────────────────────────────
def _find_env() -> Path | None:
    """Walk up from this file's directory to the repo root looking for .env."""
    here = Path(__file__).resolve().parent
    for candidate in [here, here.parent, here.parent.parent, here.parent.parent.parent]:
        p = candidate / ".env"
        if p.exists():
            return p
    return None

def _load_env() -> None:
    env_path = _find_env()
    if env_path is None:
        return
    with open(env_path) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            os.environ.setdefault(key, val)

_load_env()

# ── Connection ────────────────────────────────────────────────────────────────
def _dsn() -> str:
    host = os.environ.get("POSTGRES_HOST", "127.0.0.1")
    port = os.environ.get("POSTGRES_PORT", "5434")
    dbname = os.environ.get("POSTGRES_DB", "football")
    user = os.environ.get("POSTGRES_USER", "football")
    password = os.environ.get("POSTGRES_PASSWORD", "football")
    return (
        f"host={host} port={port} dbname={dbname} "
        f"user={user} password={password} connect_timeout=10"
    )


def query(sql: str, params: tuple | None = None) -> list[dict]:
    """Run *sql* and return rows as a list of dicts.

    Returns [] if Postgres is unreachable – pages show an empty-data message
    instead of a loader crash.
    """
    try:
        import psycopg
        from psycopg.rows import dict_row

        with psycopg.connect(_dsn(), row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchall()
    except Exception as exc:  # noqa: BLE001
        print(f"[_pg] query error: {exc}", file=sys.stderr)
        return []


def query_one(sql: str, params: tuple | None = None) -> dict:
    """Run *sql* and return the first row, or {} if no rows."""
    rows = query(sql, params)
    return rows[0] if rows else {}


def emit_json(data: object) -> None:
    """Write *data* as JSON to stdout (the data loader output)."""
    json.dump(data, sys.stdout, default=str, ensure_ascii=False)


def emit_csv(rows: list[dict], columns: list[str] | None = None) -> None:
    """Write *rows* as CSV to stdout."""
    import csv

    if not rows:
        print("", end="")
        return
    cols = columns or list(rows[0].keys())
    writer = csv.DictWriter(sys.stdout, fieldnames=cols, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
